"""Technical indicators, pure-Python over sequences.

Kept dependency-free (no numpy/pandas) so the signal path runs anywhere and is
trivially unit-testable. Each function returns the latest value, or ``None``
when there is insufficient history. No look-ahead: functions only ever read the
data passed to them.
"""

from __future__ import annotations

from typing import List, Optional, Sequence

from ..risk.models import Bar


def sma(values: Sequence[float], period: int) -> Optional[float]:
    if len(values) < period or period <= 0:
        return None
    window = values[-period:]
    return sum(window) / period


def rolling_high(values: Sequence[float], period: int) -> Optional[float]:
    if len(values) < period or period <= 0:
        return None
    return max(values[-period:])


def rolling_low(values: Sequence[float], period: int) -> Optional[float]:
    if len(values) < period or period <= 0:
        return None
    return min(values[-period:])


def rsi(closes: Sequence[float], period: int = 14) -> Optional[float]:
    """Wilder's RSI on the latest ``period`` deltas."""
    if len(closes) < period + 1:
        return None
    gains = 0.0
    losses = 0.0
    for i in range(len(closes) - period, len(closes)):
        change = closes[i] - closes[i - 1]
        if change >= 0:
            gains += change
        else:
            losses -= change
    avg_gain = gains / period
    avg_loss = losses / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def atr(bars: Sequence[Bar], period: int = 14) -> Optional[float]:
    """Average True Range over the latest ``period`` bars."""
    if len(bars) < period + 1:
        return None
    trs: List[float] = []
    for i in range(len(bars) - period, len(bars)):
        high, low, prev_close = bars[i].high, bars[i].low, bars[i - 1].close
        trs.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    return sum(trs) / period


def zscore(values: Sequence[float], period: int) -> Optional[float]:
    """Z-score of the latest value versus the trailing window."""
    if len(values) < period or period <= 1:
        return None
    window = values[-period:]
    mean = sum(window) / period
    var = sum((v - mean) ** 2 for v in window) / period
    std = var ** 0.5
    if std == 0:
        return 0.0
    return (values[-1] - mean) / std


def avg_dollar_volume(bars: Sequence[Bar], period: int = 20) -> Optional[float]:
    if len(bars) < period or period <= 0:
        return None
    window = bars[-period:]
    return sum(b.close * b.volume for b in window) / period


def avg_volume(bars: Sequence[Bar], period: int = 20) -> Optional[float]:
    """Average share volume over the trailing window (for the ADV cap)."""
    if len(bars) < period or period <= 0:
        return None
    return sum(b.volume for b in bars[-period:]) / period


def rvol(bars: Sequence[Bar], period: int = 20) -> Optional[float]:
    """Relative volume: the latest bar's volume vs the trailing average.

    The trailing window EXCLUDES the current bar, so it measures how unusual the
    current bar's participation is against its own recent baseline. Used as a
    directional-conviction input (not for sizing).
    """
    if len(bars) < period + 1 or period <= 0:
        return None
    baseline = bars[-period - 1:-1]
    avg = sum(b.volume for b in baseline) / period
    if avg <= 0:
        return None
    return bars[-1].volume / avg


def closes(bars: Sequence[Bar]) -> List[float]:
    return [b.close for b in bars]
