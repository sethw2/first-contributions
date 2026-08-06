"""In-memory simulated broker.

Used by the backtester and the unit tests. Fills market orders immediately at
the current price plus a configurable slippage, tracks cash and positions, and
honors ``client_order_id`` for idempotency. This is NOT a live broker — it is
the deterministic stand-in that lets the same engine code run in tests.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from ..risk.models import Account, Order, OrderStatus, OrderType, Side
from .broker import Broker, BrokerPosition


class PaperSimBroker(Broker):
    def __init__(self, starting_cash: float = 100_000.0,
                 slippage_bps: float = 1.0, commission_per_share: float = 0.0) -> None:
        self._cash = starting_cash
        self._start_cash = starting_cash
        self._slippage_bps = slippage_bps
        self._commission_per_share = commission_per_share
        self._positions: Dict[str, BrokerPosition] = {}
        self._prices: Dict[str, float] = {}
        self._orders: Dict[str, Order] = {}         # client_order_id -> Order
        self._realized_pnl = 0.0

    # ---- price feed (driven by the backtester / engine each bar) ----
    def update_price(self, symbol: str, price: float) -> None:
        self._prices[symbol] = price

    def update_prices(self, prices: Dict[str, float]) -> None:
        self._prices.update(prices)

    def _mark_price(self, symbol: str) -> float:
        return self._prices.get(symbol, 0.0)

    # ---- Broker interface ----
    def get_account(self) -> Account:
        equity = self._cash + sum(
            p.qty * self._mark_price(p.symbol) for p in self._positions.values()
        )
        return Account(equity=equity, cash=self._cash, buying_power=max(self._cash, 0.0))

    def get_positions(self) -> List[BrokerPosition]:
        return [p for p in self._positions.values() if abs(p.qty) > 1e-9]

    def get_open_orders(self) -> List[Order]:
        return [o for o in self._orders.values() if o.is_open]

    def submit_order(self, order: Order) -> Order:
        # Idempotency: a repeated client_order_id returns the existing order.
        if order.client_order_id and order.client_order_id in self._orders:
            return self._orders[order.client_order_id]

        price = self._fill_price(order)
        if price <= 0:
            order.status = OrderStatus.REJECTED
            order.reason = (order.reason + " | no market price").strip(" |")
            if order.client_order_id:
                self._orders[order.client_order_id] = order
            return order

        signed_qty = order.qty * order.side.sign
        self._apply_fill(order.symbol, signed_qty, price)
        commission = abs(order.qty) * self._commission_per_share
        self._cash -= commission

        order.status = OrderStatus.FILLED
        order.filled_qty = order.qty
        order.filled_avg_price = price
        order.broker_order_id = f"sim-{len(self._orders) + 1}"
        if order.client_order_id:
            self._orders[order.client_order_id] = order
        return order

    def cancel_order(self, broker_order_id: str) -> None:
        for o in self._orders.values():
            if o.broker_order_id == broker_order_id and o.is_open:
                o.status = OrderStatus.CANCELED

    def cancel_all_orders(self) -> None:
        for o in self._orders.values():
            if o.is_open:
                o.status = OrderStatus.CANCELED

    def close_position(self, symbol: str) -> None:
        pos = self._positions.get(symbol)
        if not pos or abs(pos.qty) < 1e-9:
            return
        side = Side.SELL if pos.qty > 0 else Side.BUY
        self.submit_order(Order(symbol=symbol, side=side, qty=abs(pos.qty),
                                order_type=OrderType.MARKET,
                                client_order_id=f"close-{symbol}-{len(self._orders)}",
                                reason="close_position"))

    # ---- internals ----
    def _fill_price(self, order: Order) -> float:
        base = self._mark_price(order.symbol)
        if base <= 0:
            base = order.limit_price or 0.0
        if base <= 0:
            return 0.0
        slip = base * (self._slippage_bps / 10_000.0)
        return base + slip if order.side is Side.BUY else base - slip

    def _apply_fill(self, symbol: str, signed_qty: float, price: float) -> None:
        pos = self._positions.get(symbol)
        self._cash -= signed_qty * price
        if pos is None:
            self._positions[symbol] = BrokerPosition(symbol, signed_qty, price)
            return
        new_qty = pos.qty + signed_qty
        if pos.qty != 0 and (pos.qty > 0) != (signed_qty > 0):
            # reducing/closing: realize P&L on the closed portion
            closed = min(abs(signed_qty), abs(pos.qty))
            direction = 1 if pos.qty > 0 else -1
            self._realized_pnl += closed * (price - pos.avg_entry_price) * direction
        if abs(new_qty) < 1e-9:
            del self._positions[symbol]
        elif (pos.qty > 0) == (new_qty > 0) and abs(new_qty) > abs(pos.qty):
            # adding to the position: blend the average price
            total_cost = pos.avg_entry_price * abs(pos.qty) + price * abs(signed_qty)
            pos.avg_entry_price = total_cost / abs(new_qty)
            pos.qty = new_qty
        else:
            pos.qty = new_qty

    @property
    def realized_pnl(self) -> float:
        return self._realized_pnl

    @property
    def filled_order_count(self) -> int:
        from ..risk.models import OrderStatus
        return sum(1 for o in self._orders.values() if o.status == OrderStatus.FILLED)
