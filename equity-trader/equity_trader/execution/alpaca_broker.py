"""Alpaca broker adapter.

Wraps ``alpaca-py`` behind the same ``Broker`` interface. The dependency is
imported lazily so the rest of the system (and the whole test suite) runs
without it installed.

Safety: this adapter enforces the paper/live guard. Constructing a LIVE client
requires (a) ``environment == "live"``, (b) explicit ``i_understand_live=True``,
and (c) an interactive confirmation unless ``require_confirmation=False`` is
passed deliberately. Paper is the default on any ambiguity.
"""

from __future__ import annotations

from typing import List, Optional

from ..config.settings import Environment, Settings
from ..risk.models import Account, Order, OrderStatus, OrderType, Side
from .broker import Broker, BrokerPosition

_PAPER_URL = "https://paper-api.alpaca.markets"
_LIVE_URL = "https://api.alpaca.markets"


class LiveTradingGuardError(RuntimeError):
    """Raised when a live client is requested without explicit authorization."""


class AlpacaBroker(Broker):
    def __init__(self, settings: Settings, i_understand_live: bool = False,
                 require_confirmation: bool = True) -> None:
        self.settings = settings
        self._live = settings.is_live
        if self._live:
            self._authorize_live(i_understand_live, require_confirmation)

        if not settings.api_key or not settings.api_secret:
            raise RuntimeError(
                "ALPACA_API_KEY / ALPACA_API_SECRET must be set in the environment."
            )
        try:
            from alpaca.trading.client import TradingClient  # lazy import
        except ImportError as exc:  # pragma: no cover - depends on optional dep
            raise ImportError(
                "alpaca-py is required for live/paper trading. "
                "Install with: pip install alpaca-py"
            ) from exc

        self._client = TradingClient(
            api_key=settings.api_key,
            secret_key=settings.api_secret,
            paper=not self._live,
        )
        self._base_url = _LIVE_URL if self._live else _PAPER_URL

    # ------------------------------------------------------------- live guard
    @staticmethod
    def _authorize_live(i_understand_live: bool, require_confirmation: bool) -> None:
        if not i_understand_live:
            raise LiveTradingGuardError(
                "Refusing to construct a LIVE broker: pass i_understand_live=True "
                "AND set environment='live' deliberately. Default is paper."
            )
        if require_confirmation:
            resp = input(
                "\n*** LIVE TRADING with REAL MONEY is about to be enabled. ***\n"
                "Type exactly 'ENABLE LIVE TRADING' to proceed: "
            )
            if resp.strip() != "ENABLE LIVE TRADING":
                raise LiveTradingGuardError("Live trading not confirmed; aborting.")

    # ------------------------------------------------------------- interface
    def get_account(self) -> Account:
        a = self._client.get_account()
        return Account(
            equity=float(a.equity),
            cash=float(a.cash),
            buying_power=float(a.buying_power),
            is_pattern_day_trader=bool(getattr(a, "pattern_day_trader", False)),
        )

    def get_positions(self) -> List[BrokerPosition]:
        out = []
        for p in self._client.get_all_positions():
            out.append(BrokerPosition(
                symbol=p.symbol,
                qty=float(p.qty),
                avg_entry_price=float(p.avg_entry_price),
            ))
        return out

    def get_open_orders(self) -> List[Order]:
        from alpaca.trading.requests import GetOrdersRequest
        from alpaca.trading.enums import QueryOrderStatus
        req = GetOrdersRequest(status=QueryOrderStatus.OPEN)
        return [self._to_order(o) for o in self._client.get_orders(req)]

    def submit_order(self, order: Order) -> Order:
        from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest
        from alpaca.trading.enums import OrderSide, TimeInForce

        side = OrderSide.BUY if order.side is Side.BUY else OrderSide.SELL
        common = dict(
            symbol=order.symbol,
            qty=order.qty,
            side=side,
            time_in_force=TimeInForce.DAY,
            client_order_id=order.client_order_id,  # idempotency key
        )
        if order.order_type is OrderType.LIMIT:
            req = LimitOrderRequest(limit_price=order.limit_price, **common)
        else:
            req = MarketOrderRequest(**common)
        submitted = self._client.submit_order(req)
        return self._to_order(submitted)

    def cancel_order(self, broker_order_id: str) -> None:
        self._client.cancel_order_by_id(broker_order_id)

    def cancel_all_orders(self) -> None:
        self._client.cancel_orders()

    def close_position(self, symbol: str) -> None:
        self._client.close_position(symbol)

    def close_all_positions(self) -> None:
        self._client.close_all_positions(cancel_orders=True)

    # ------------------------------------------------------------- helpers
    @staticmethod
    def _to_order(o) -> Order:
        status_map = {
            "new": OrderStatus.SUBMITTED,
            "accepted": OrderStatus.SUBMITTED,
            "partially_filled": OrderStatus.PARTIALLY_FILLED,
            "filled": OrderStatus.FILLED,
            "canceled": OrderStatus.CANCELED,
            "rejected": OrderStatus.REJECTED,
        }
        return Order(
            symbol=o.symbol,
            side=Side.BUY if str(o.side).endswith("buy") else Side.SELL,
            qty=float(o.qty),
            client_order_id=o.client_order_id,
            broker_order_id=str(o.id),
            status=status_map.get(str(o.status).split(".")[-1].lower(), OrderStatus.SUBMITTED),
            filled_qty=float(o.filled_qty or 0),
            filled_avg_price=float(o.filled_avg_price or 0),
        )
