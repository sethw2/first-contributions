from datetime import datetime, timedelta, timezone

import pytest

from equity_trader.risk.models import Bar
from equity_trader.strategy import indicators as ind


def bars_from_closes(closes, vol=1_000_000):
    out = []
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    prev = closes[0]
    for i, c in enumerate(closes):
        hi = max(prev, c) + 0.5
        lo = min(prev, c) - 0.5
        out.append(Bar(t0 + timedelta(days=i), open=prev, high=hi, low=lo,
                       close=c, volume=vol))
        prev = c
    return out


def test_sma_and_insufficient_history():
    assert ind.sma([1, 2, 3, 4], 2) == pytest.approx(3.5)
    assert ind.sma([1], 2) is None


def test_rolling_high_low():
    vals = [1, 5, 3, 9, 2]
    assert ind.rolling_high(vals, 3) == 9
    assert ind.rolling_low(vals, 3) == 2


def test_rsi_all_gains_is_100():
    closes = list(range(1, 20))  # strictly increasing
    assert ind.rsi(closes, 14) == pytest.approx(100.0)


def test_rsi_midrange_for_alternating():
    closes = [10, 11, 10, 11, 10, 11, 10, 11, 10, 11, 10, 11, 10, 11, 10]
    r = ind.rsi(closes, 14)
    assert 0 < r < 100


def test_atr_positive():
    bars = bars_from_closes([10, 11, 12, 11, 13, 12, 14, 13, 15, 14, 16, 15, 17, 16, 18])
    a = ind.atr(bars, 14)
    assert a is not None and a > 0


def test_zscore_sign():
    vals = [10] * 19 + [20]  # last value well above the mean
    z = ind.zscore(vals, 20)
    assert z > 0


def test_avg_dollar_volume():
    bars = bars_from_closes([100] * 20, vol=1_000_000)
    assert ind.avg_dollar_volume(bars, 20) == pytest.approx(100_000_000)
