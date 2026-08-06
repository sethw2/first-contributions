import pytest

from equity_trader.execution.paper_sim import PaperSimBroker
from equity_trader.risk.models import Order, OrderStatus, OrderType, Side


def buy(symbol, qty, coid):
    return Order(symbol=symbol, side=Side.BUY, qty=qty,
                 order_type=OrderType.MARKET, client_order_id=coid)


def test_market_buy_fills_and_reduces_cash():
    b = PaperSimBroker(starting_cash=100_000, slippage_bps=0.0)
    b.update_price("AAPL", 100.0)
    order = b.submit_order(buy("AAPL", 10, "c1"))
    assert order.status == OrderStatus.FILLED
    assert order.filled_avg_price == pytest.approx(100.0)
    acct = b.get_account()
    assert acct.cash == pytest.approx(99_000.0)
    assert acct.equity == pytest.approx(100_000.0)  # cash + position mark


def test_slippage_moves_buy_price_up():
    b = PaperSimBroker(starting_cash=100_000, slippage_bps=10.0)  # 10 bps
    b.update_price("AAPL", 100.0)
    order = b.submit_order(buy("AAPL", 1, "c1"))
    assert order.filled_avg_price == pytest.approx(100.1)


def test_idempotent_client_order_id():
    b = PaperSimBroker(starting_cash=100_000, slippage_bps=0.0)
    b.update_price("AAPL", 100.0)
    b.submit_order(buy("AAPL", 10, "dup"))
    b.submit_order(buy("AAPL", 10, "dup"))  # same id -> no second fill
    positions = b.get_positions()
    assert len(positions) == 1
    assert positions[0].qty == 10


def test_average_price_blends_on_add():
    b = PaperSimBroker(starting_cash=1_000_000, slippage_bps=0.0)
    b.update_price("AAPL", 100.0)
    b.submit_order(buy("AAPL", 10, "c1"))
    b.update_price("AAPL", 110.0)
    b.submit_order(buy("AAPL", 10, "c2"))
    pos = b.get_positions()[0]
    assert pos.qty == 20
    assert pos.avg_entry_price == pytest.approx(105.0)


def test_close_position_realizes_pnl():
    b = PaperSimBroker(starting_cash=100_000, slippage_bps=0.0)
    b.update_price("AAPL", 100.0)
    b.submit_order(buy("AAPL", 10, "c1"))
    b.update_price("AAPL", 120.0)
    b.close_position("AAPL")
    assert b.get_positions() == []
    assert b.realized_pnl == pytest.approx(200.0)  # 10 * (120-100)


def test_rejects_when_no_price():
    b = PaperSimBroker(starting_cash=100_000)
    order = b.submit_order(buy("UNKNOWN", 10, "c1"))
    assert order.status == OrderStatus.REJECTED
