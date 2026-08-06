"""Core domain models shared across the whole system.

Deliberately pure-stdlib (no numpy/pandas) so the risk layer and its tests run
in any environment. Strategy and backtest modules may use heavier libraries;
the risk core must not.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"

    @property
    def sign(self) -> int:
        """+1 for a long side, -1 for a short side."""
        return 1 if self is Side.BUY else -1


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderStatus(str, Enum):
    NEW = "new"                      # created locally, not yet sent
    SUBMITTED = "submitted"          # accepted by broker
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELED = "canceled"
    REJECTED = "rejected"

    @property
    def is_terminal(self) -> bool:
        return self in (OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.REJECTED)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Bar:
    """A single OHLCV price bar."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    @property
    def dollar_volume(self) -> float:
        return self.close * self.volume


@dataclass
class Order:
    """A trading order and its lifecycle state.

    ``client_order_id`` is the idempotency key: the same logical intent must
    always carry the same id so retries never double-fill.
    """

    symbol: str
    side: Side
    qty: float
    order_type: OrderType = OrderType.MARKET
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    client_order_id: Optional[str] = None
    status: OrderStatus = OrderStatus.NEW
    filled_qty: float = 0.0
    filled_avg_price: float = 0.0
    broker_order_id: Optional[str] = None
    created_at: datetime = field(default_factory=_utcnow)
    reason: str = ""  # why the system placed this order (for the audit log)

    @property
    def is_open(self) -> bool:
        return not self.status.is_terminal

    @property
    def notional(self) -> float:
        ref = self.limit_price or self.filled_avg_price
        return abs(self.qty) * ref if ref else 0.0


@dataclass
class Position:
    """An open position with its mandated exits.

    Per the spec, no position may exist without a hard stop and a time stop.
    ``time_stop`` is the absolute deadline (<= 2 weeks from entry) at which the
    engine force-exits regardless of price.
    """

    symbol: str
    qty: float                       # signed: positive long, negative short
    avg_entry_price: float
    entry_time: datetime
    stop_price: float                # hard price stop (mandatory)
    time_stop: datetime              # absolute time-based exit (mandatory)
    take_profit: Optional[float] = None
    kind: str = ""                   # "momentum" | "reversion" | ...

    @property
    def side(self) -> Side:
        return Side.BUY if self.qty >= 0 else Side.SELL

    @property
    def is_long(self) -> bool:
        return self.qty > 0

    def market_value(self, price: float) -> float:
        return self.qty * price

    def unrealized_pnl(self, price: float) -> float:
        return (price - self.avg_entry_price) * self.qty

    def stop_distance(self) -> float:
        """Absolute per-share distance from entry to the hard stop."""
        return abs(self.avg_entry_price - self.stop_price)

    def is_time_stopped(self, now: datetime) -> bool:
        return now >= self.time_stop

    def is_price_stopped(self, price: float) -> bool:
        if self.is_long:
            return price <= self.stop_price
        return price >= self.stop_price


@dataclass
class Account:
    """A snapshot of broker account state."""

    equity: float                    # total portfolio value
    cash: float
    buying_power: float
    currency: str = "USD"
    is_pattern_day_trader: bool = False
    timestamp: datetime = field(default_factory=_utcnow)
