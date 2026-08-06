"""Broker abstraction.

The engine and backtester depend only on this interface, so the ONLY difference
between a backtest, paper trading, and live trading is which adapter is injected.
That is what keeps backtest results honest — the same strategy and risk code
runs against all three.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import List

from ..risk.models import Account, Order


@dataclass
class BrokerPosition:
    """Raw position as the broker reports it (no strategy-level stops)."""

    symbol: str
    qty: float               # signed
    avg_entry_price: float

    @property
    def notional(self) -> float:
        return abs(self.qty) * self.avg_entry_price


class Broker(abc.ABC):
    """Minimal broker surface the system relies on."""

    @abc.abstractmethod
    def get_account(self) -> Account: ...

    @abc.abstractmethod
    def get_positions(self) -> List[BrokerPosition]: ...

    @abc.abstractmethod
    def get_open_orders(self) -> List[Order]: ...

    @abc.abstractmethod
    def submit_order(self, order: Order) -> Order:
        """Submit an order. Implementations MUST honor ``client_order_id`` for
        idempotency: resubmitting the same id must not create a second order."""

    @abc.abstractmethod
    def cancel_order(self, broker_order_id: str) -> None: ...

    @abc.abstractmethod
    def cancel_all_orders(self) -> None: ...

    @abc.abstractmethod
    def close_position(self, symbol: str) -> None: ...

    def close_all_positions(self) -> None:
        for pos in self.get_positions():
            self.close_position(pos.symbol)
