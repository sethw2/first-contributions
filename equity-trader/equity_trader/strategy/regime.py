"""Market regime filter.

Classifies the broad market so the strategy takes momentum only when the tape
supports it and leans defensive otherwise. Uses a benchmark (default SPY):
above its long trend = risk-on; below = risk-off.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, List

from ..risk.models import Bar
from .indicators import closes, sma


class Regime(str, Enum):
    RISK_ON = "risk_on"
    RISK_OFF = "risk_off"
    UNKNOWN = "unknown"


def classify(market: Dict[str, List[Bar]], benchmark: str = "SPY",
             trend_lookback: int = 200) -> Regime:
    bars = market.get(benchmark)
    if not bars:
        return Regime.UNKNOWN
    c = closes(bars)
    trend = sma(c, trend_lookback)
    if trend is None:
        return Regime.UNKNOWN
    return Regime.RISK_ON if c[-1] >= trend else Regime.RISK_OFF
