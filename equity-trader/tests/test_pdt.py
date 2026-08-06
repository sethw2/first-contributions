from datetime import datetime, timezone

from equity_trader.risk.pdt import PDTTracker


def _dt(y, m, d, h=10):
    return datetime(y, m, d, h, tzinfo=timezone.utc)


def test_open_then_same_day_close_is_a_day_trade():
    pdt = PDTTracker(equity_threshold=25_000, max_day_trades=3)
    t = _dt(2026, 8, 3)  # Monday
    pdt.record_open("AAPL", t)
    assert pdt.would_be_day_trade("AAPL", t) is True
    pdt.record_close("AAPL", t)
    assert pdt.day_trades_in_window(t.date()) == 1


def test_close_next_day_is_not_a_day_trade():
    pdt = PDTTracker()
    pdt.record_open("AAPL", _dt(2026, 8, 3))
    pdt.record_close("AAPL", _dt(2026, 8, 4))  # Tuesday
    assert pdt.day_trades_in_window(_dt(2026, 8, 4).date()) == 0


def test_limit_enforced_below_threshold():
    pdt = PDTTracker(equity_threshold=25_000, max_day_trades=3)
    day = _dt(2026, 8, 3)
    for i in range(3):
        pdt.record_open("SPY", day)
        pdt.record_close("SPY", day)
    assert pdt.can_day_trade(account_equity=20_000, as_of=day) is False


def test_above_threshold_is_unrestricted():
    pdt = PDTTracker(equity_threshold=25_000, max_day_trades=3)
    day = _dt(2026, 8, 3)
    for i in range(5):
        pdt.record_open("SPY", day)
        pdt.record_close("SPY", day)
    assert pdt.can_day_trade(account_equity=30_000, as_of=day) is True


def test_old_day_trades_roll_off_window():
    pdt = PDTTracker(equity_threshold=25_000, max_day_trades=3, window_business_days=5)
    old = _dt(2026, 7, 1)
    pdt.record_open("SPY", old)
    pdt.record_close("SPY", old)
    later = _dt(2026, 8, 3)
    assert pdt.day_trades_in_window(later.date()) == 0
