"""TradingEngine — the shared decision core.

Runs ONE trading cycle: reconcile once at startup, then per cycle check the
kill switch and circuit breaker, process exits, then size/validate/submit
entries. The backtester and the live loop both call ``run_cycle`` with the same
strategy and risk objects — only the injected broker and clock differ.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from ..config.settings import Settings
from ..execution.broker import Broker
from ..execution.reconcile import reconcile
from ..risk.manager import RiskManager
from ..risk.models import Account, Order, OrderType, Position, Side
from ..strategy.base import Signal, Strategy

log = logging.getLogger("equity_trader.engine")


class TradingEngine:
    def __init__(self, settings: Settings, broker: Broker, strategy: Strategy,
                 risk: RiskManager) -> None:
        self.settings = settings
        self.broker = broker
        self.strategy = strategy
        self.risk = risk
        self.positions: Dict[str, Position] = {}
        self._cycle = 0

    # ------------------------------------------------------------- startup
    def startup(self) -> None:
        report = reconcile(self.broker, self.positions)
        if not report.clean:
            log.warning("reconcile: orphaned_local=%s untracked_broker=%s",
                        report.orphaned_local, report.untracked_broker)
        if report.canceled_open_orders:
            log.info("reconcile: canceled %d stray open orders", report.canceled_open_orders)
        self.risk.start_session(self.broker.get_account())
        log.info("engine started: environment=%s equity=%.2f",
                 self.settings.environment, self.risk.session_start_equity or 0.0)

    # ------------------------------------------------------------- one cycle
    def run_cycle(self, market: Dict[str, List], now) -> None:
        self._cycle += 1
        self._sync_prices(market)
        account = self.broker.get_account()

        if self.risk.kill_switch.is_tripped:
            log.error("KILL SWITCH tripped (%s): canceling orders, no new trades",
                      self.risk.kill_switch.reason)
            self.broker.cancel_all_orders()
            return

        if self.risk.check_circuit_breaker(account):
            log.error("CIRCUIT BREAKER: session P&L %.2f%% -> flatten & halt",
                      self.risk.session_pnl_pct(account) * 100)
            self._flatten_all(market, now, "circuit_breaker")
            return

        self._process_exits(market, now)
        self._process_entries(market, now, account)

    # ------------------------------------------------------------- exits
    def _process_exits(self, market: Dict[str, List], now) -> None:
        for symbol in list(self.positions.keys()):
            pos = self.positions[symbol]
            bars = market.get(symbol)
            if not bars:
                continue
            price = bars[-1].close
            reason = self._exit_reason(pos, bars, price, now)
            if reason:
                self._close(symbol, now, reason)

    def _exit_reason(self, pos: Position, bars: List, price: float, now) -> Optional[str]:
        if pos.is_price_stopped(price):
            return "hard_stop"
        if pos.is_time_stopped(now):
            return "time_stop"
        if pos.take_profit is not None:
            if (pos.is_long and price >= pos.take_profit) or \
               (not pos.is_long and price <= pos.take_profit):
                return "take_profit"
        strat_exit = self.strategy.should_exit(pos, bars, now)
        if strat_exit:
            return strat_exit
        return None

    def _close(self, symbol: str, now, reason: str) -> None:
        pos = self.positions.get(symbol)
        if not pos:
            return
        self.broker.close_position(symbol)
        self.risk.register_close(symbol, now)
        log.info("EXIT %s qty=%.0f reason=%s", symbol, pos.qty, reason)
        self.positions.pop(symbol, None)

    def _flatten_all(self, market, now, reason: str) -> None:
        for symbol in list(self.positions.keys()):
            self._close(symbol, now, reason)

    # ------------------------------------------------------------- entries
    def _process_entries(self, market: Dict[str, List], now, account: Account) -> None:
        open_symbols = list(self.positions.keys())
        signals = self.strategy.generate_signals(market, now, open_symbols)
        for sig in signals:
            if len(self.positions) >= self.risk.limits.max_concurrent_positions:
                break
            self._try_enter(sig, now, account)

    def _try_enter(self, sig: Signal, now, account: Account) -> None:
        stop, take_profit, time_stop = self.risk.compute_stops(
            sig.side, sig.reference_price, sig.atr, now)
        qty = self.risk.size_position(account.equity, sig.reference_price, stop,
                                      avg_daily_volume=sig.avg_volume)
        if qty <= 0:
            return

        order = Order(
            symbol=sig.symbol, side=sig.side, qty=qty, order_type=OrderType.MARKET,
            limit_price=sig.reference_price,  # reference for the notional check
            client_order_id=f"{sig.symbol}-{now.isoformat()}-entry",
            reason=f"{sig.kind}: {sig.reason}",
        )
        decision = self.risk.validate_entry(order, account, list(self.positions.values()), now)
        if not decision.approved:
            log.debug("entry rejected %s: %s (%s)", sig.symbol, decision.reason, decision.detail)
            return

        filled = self.broker.submit_order(order)
        if filled.status.name != "FILLED":
            log.warning("order not filled %s: %s", sig.symbol, filled.status)
            return

        signed_qty = filled.filled_qty * sig.side.sign
        self.positions[sig.symbol] = Position(
            symbol=sig.symbol, qty=signed_qty, avg_entry_price=filled.filled_avg_price,
            entry_time=now, stop_price=stop, time_stop=time_stop,
            take_profit=take_profit, kind=sig.kind,
        )
        self.risk.register_open(sig.symbol, now)
        log.info("ENTER %s qty=%.0f @ %.2f stop=%.2f tp=%.2f kind=%s",
                 sig.symbol, signed_qty, filled.filled_avg_price, stop,
                 take_profit or 0.0, sig.kind)

    # ------------------------------------------------------------- helpers
    def _sync_prices(self, market: Dict[str, List]) -> None:
        if hasattr(self.broker, "update_prices"):
            self.broker.update_prices(
                {s: bars[-1].close for s, bars in market.items() if bars}
            )
