"""The RiskManager — the single gate every order passes through.

Nothing in ``strategy/`` or ``engine/`` is allowed to size or place an order
directly. Sizing is derived from a risk budget; every entry is validated against
hard exposure, notional, PDT, circuit-breaker, and kill-switch limits. On any
ambiguity the answer is "no trade."
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import List, Optional

from ..config.settings import RiskLimits
from .kill_switch import KillSwitch
from .models import Account, Order, Position, Side
from .pdt import PDTTracker


class RejectReason(str, Enum):
    OK = "ok"
    KILL_SWITCH = "kill_switch_tripped"
    CIRCUIT_BREAKER = "daily_loss_circuit_breaker"
    SHORTING_DISABLED = "shorting_disabled"
    MAX_POSITIONS = "max_concurrent_positions"
    POSITION_NOTIONAL = "per_symbol_notional_cap"
    GROSS_EXPOSURE = "max_gross_exposure"
    BUYING_POWER = "insufficient_buying_power"
    PDT_LIMIT = "pdt_day_trade_limit"
    ZERO_QTY = "zero_or_negative_qty"
    BAD_STOP = "invalid_stop_distance"


@dataclass
class RiskDecision:
    approved: bool
    reason: RejectReason
    detail: str = ""

    @classmethod
    def ok(cls) -> "RiskDecision":
        return cls(True, RejectReason.OK)

    @classmethod
    def reject(cls, reason: RejectReason, detail: str = "") -> "RiskDecision":
        return cls(False, reason, detail)


class RiskManager:
    def __init__(self, limits: RiskLimits, kill_switch: KillSwitch,
                 pdt_tracker: Optional[PDTTracker] = None) -> None:
        self.limits = limits
        self.kill_switch = kill_switch
        self.pdt = pdt_tracker or PDTTracker(
            equity_threshold=limits.pdt_equity_threshold,
            max_day_trades=limits.pdt_max_day_trades,
        )
        self.session_start_equity: Optional[float] = None
        self.halted_for_session = False

    # ------------------------------------------------------------------ session
    def start_session(self, account: Account) -> None:
        """Anchor the daily circuit breaker to the session's opening equity."""
        self.session_start_equity = account.equity
        self.halted_for_session = False

    def session_pnl_pct(self, account: Account) -> float:
        if not self.session_start_equity:
            return 0.0
        return (account.equity - self.session_start_equity) / self.session_start_equity

    def check_circuit_breaker(self, account: Account) -> bool:
        """Return True if the daily loss limit is breached (caller must flatten & halt)."""
        if self.session_pnl_pct(account) <= -abs(self.limits.daily_loss_limit):
            self.halted_for_session = True
        return self.halted_for_session

    # ------------------------------------------------------------------- sizing
    def size_position(self, equity: float, entry_price: float, stop_price: float) -> int:
        """Whole-share size from the risk budget, capped by the notional limit.

        shares = (equity * risk_per_trade) / per-share-stop-distance,
        then clipped so a single symbol never exceeds ``max_position_notional_pct``.
        Returns 0 when inputs are invalid (never raises into strategy code).
        """
        if entry_price <= 0:
            return 0
        stop_distance = abs(entry_price - stop_price)
        if stop_distance <= 0:
            return 0
        risk_budget = equity * self.limits.risk_per_trade
        shares_by_risk = risk_budget / stop_distance
        max_notional = equity * self.limits.max_position_notional_pct
        shares_by_notional = max_notional / entry_price
        return max(0, int(math.floor(min(shares_by_risk, shares_by_notional))))

    def compute_stops(self, side: Side, entry_price: float, atr: float,
                      entry_time: datetime) -> "tuple[float, float, datetime]":
        """Return (hard_stop, take_profit, time_stop) for a new position."""
        k = self.limits.atr_stop_multiple
        tp_k = self.limits.atr_stop_multiple * 1.5
        if side is Side.BUY:
            stop = entry_price - k * atr
            take_profit = entry_price + tp_k * atr
        else:
            stop = entry_price + k * atr
            take_profit = entry_price - tp_k * atr
        time_stop = entry_time + timedelta(days=self.limits.max_holding_days)
        return stop, take_profit, time_stop

    # --------------------------------------------------------------- validation
    def validate_entry(self, order: Order, account: Account,
                       positions: List[Position], now: datetime) -> RiskDecision:
        """Gate a new-position order against every hard limit. Entries only."""
        if self.kill_switch.is_tripped:
            return RiskDecision.reject(RejectReason.KILL_SWITCH, self.kill_switch.reason)
        if self.halted_for_session or self.check_circuit_breaker(account):
            return RiskDecision.reject(RejectReason.CIRCUIT_BREAKER,
                                       f"session P&L {self.session_pnl_pct(account):.2%}")
        if order.qty <= 0:
            return RiskDecision.reject(RejectReason.ZERO_QTY)
        if order.side is Side.SELL and not self.limits.allow_shorting:
            return RiskDecision.reject(RejectReason.SHORTING_DISABLED)

        if len(positions) >= self.limits.max_concurrent_positions:
            return RiskDecision.reject(RejectReason.MAX_POSITIONS,
                                       f"{len(positions)}/{self.limits.max_concurrent_positions}")

        ref_price = order.limit_price or order.stop_price or 0.0
        if ref_price <= 0:
            return RiskDecision.reject(RejectReason.BAD_STOP, "no reference price for notional check")
        new_notional = order.qty * ref_price

        if new_notional > account.equity * self.limits.max_position_notional_pct + 1e-6:
            return RiskDecision.reject(RejectReason.POSITION_NOTIONAL,
                                       f"{new_notional:.0f} > {account.equity * self.limits.max_position_notional_pct:.0f}")

        gross = sum(abs(p.qty) * p.avg_entry_price for p in positions) + new_notional
        if gross > account.equity * self.limits.max_gross_exposure + 1e-6:
            return RiskDecision.reject(RejectReason.GROSS_EXPOSURE,
                                       f"gross {gross:.0f} > {account.equity * self.limits.max_gross_exposure:.0f}")

        if new_notional > account.buying_power + 1e-6:
            return RiskDecision.reject(RejectReason.BUYING_POWER,
                                       f"{new_notional:.0f} > {account.buying_power:.0f}")

        # PDT: if the account is below threshold and its day-trade budget is spent,
        # refuse NEW intraday entries — a same-day stop-out would breach the rule.
        if not self.pdt.can_day_trade(account.equity, now):
            return RiskDecision.reject(RejectReason.PDT_LIMIT,
                                       f"{self.pdt.day_trades_in_window(now.date())}/{self.limits.pdt_max_day_trades} day trades used")

        return RiskDecision.ok()

    def validate_exit(self, order: Order, account: Account, now: datetime) -> RiskDecision:
        """Exits reduce risk and are never blocked (except by a raw sanity check).

        Note: we do NOT block an exit on PDT — being flat is always safer than
        holding to preserve a day-trade count.
        """
        if order.qty <= 0:
            return RiskDecision.reject(RejectReason.ZERO_QTY)
        return RiskDecision.ok()

    def register_open(self, symbol: str, now: datetime) -> None:
        self.pdt.record_open(symbol, now)

    def register_close(self, symbol: str, now: datetime) -> None:
        self.pdt.record_close(symbol, now)
