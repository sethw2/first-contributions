"""v1 strategy: regime-filtered momentum / mean-reversion hybrid (long-only).

- RISK_ON  : short-term breakouts with volume confirmation (momentum leg).
- RISK_OFF : stand aside on momentum; take only oversold pullbacks in names
             still in their own long-term uptrend (mean-reversion leg).
- UNKNOWN  : no new entries.

Every threshold is a named parameter from ``StrategyParams`` — no magic numbers.
Keep it simple and explainable; alpha refinement is a later phase.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from ..config.settings import StrategyParams, UniverseConfig
from ..risk.models import Bar, Position, Side
from .base import Signal, Strategy
from .indicators import (
    atr,
    avg_dollar_volume,
    closes,
    rolling_high,
    rolling_low,
    rsi,
    sma,
    zscore,
)
from .regime import Regime, classify


class MomentumReversionStrategy(Strategy):
    name = "momentum_reversion_v1"

    def __init__(self, params: StrategyParams, universe: UniverseConfig,
                 benchmark: str = "SPY") -> None:
        self.p = params
        self.universe = universe
        self.benchmark = benchmark

    def generate_signals(self, market: Dict[str, List[Bar]], now: datetime,
                         open_symbols: List[str]) -> List[Signal]:
        regime = classify(market, self.benchmark, self.p.trend_lookback)
        if regime is Regime.UNKNOWN:
            return []

        signals: List[Signal] = []
        for symbol, bars in market.items():
            if symbol in open_symbols or symbol == self.benchmark:
                continue
            if not self._liquid_enough(bars):
                continue
            sig = self._signal_for(symbol, bars, regime)
            if sig is not None:
                signals.append(sig)

        signals.sort(key=lambda s: s.strength, reverse=True)
        return signals[: self.p.max_new_positions_per_cycle]

    # --------------------------------------------------------------- helpers
    def _liquid_enough(self, bars: List[Bar]) -> bool:
        adv = avg_dollar_volume(bars, 20)
        if adv is None or adv < self.universe.min_avg_dollar_volume:
            return False
        return bars[-1].close >= self.universe.min_price

    def _signal_for(self, symbol: str, bars: List[Bar], regime: Regime) -> Optional[Signal]:
        c = closes(bars)
        a = atr(bars, self.p.atr_period)
        if a is None or a <= 0:
            return None
        last = bars[-1]

        if regime is Regime.RISK_ON:
            return self._momentum(symbol, bars, c, a, last)
        return self._reversion(symbol, bars, c, a, last)

    def _momentum(self, symbol, bars, c, a, last) -> Optional[Signal]:
        prior_high = rolling_high(c[:-1], self.p.breakout_lookback)
        if prior_high is None or last.close <= prior_high:
            return None
        avg_vol = sum(b.volume for b in bars[-self.p.breakout_lookback:]) / self.p.breakout_lookback
        if avg_vol <= 0 or last.volume < self.p.volume_confirm_multiple * avg_vol:
            return None
        # strength: breakout distance in ATRs, capped to 0..1
        strength = min(1.0, (last.close - prior_high) / a)
        return Signal(symbol=symbol, side=Side.BUY, strength=max(0.05, strength),
                      reference_price=last.close, atr=a, kind="momentum",
                      reason=f"breakout>{self.p.breakout_lookback}d high with volume confirm")

    def _reversion(self, symbol, bars, c, a, last) -> Optional[Signal]:
        trend = sma(c, self.p.trend_lookback)
        if trend is None or last.close < trend:
            return None  # only buy dips in names still in an uptrend
        r = rsi(c, self.p.rsi_period)
        z = zscore(c, self.p.zscore_lookback)
        if r is None or z is None:
            return None
        if r > self.p.rsi_oversold or z > self.p.zscore_entry:
            return None
        # strength: deeper oversold = stronger, capped to 0..1
        strength = min(1.0, abs(z) / 3.0)
        return Signal(symbol=symbol, side=Side.BUY, strength=max(0.05, strength),
                      reference_price=last.close, atr=a, kind="reversion",
                      reason=f"oversold pullback (RSI {r:.0f}, z {z:.2f}) in uptrend")

    def should_exit(self, position: Position, bars: List[Bar], now: datetime) -> Optional[str]:
        c = closes(bars)
        if position.kind == "momentum":
            low = rolling_low(c[:-1], self.p.breakout_lookback)
            if low is not None and bars[-1].close < low:
                return "momentum invalidated: closed below breakout window low"
        elif position.kind == "reversion":
            r = rsi(c, self.p.rsi_period)
            if r is not None and r >= 50.0:
                return "reversion complete: RSI recovered to 50"
        return None
