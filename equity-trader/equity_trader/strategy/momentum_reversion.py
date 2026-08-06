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
    avg_volume,
    closes,
    rolling_high,
    rolling_low,
    rsi,
    rvol,
    sma,
    zscore,
)
from .regime import Regime, classify


def _fmt(rv: Optional[float]) -> str:
    return f"{rv:.1f}x" if rv is not None else "n/a"


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

        sig = (self._momentum(symbol, bars, c, a, last) if regime is Regime.RISK_ON
               else self._reversion(symbol, bars, c, a, last))
        if sig is not None:
            # Attach avg daily volume (shares) for the RiskManager's ADV cap.
            sig.avg_volume = avg_volume(bars, 20) or 0.0
        return sig

    def _momentum(self, symbol, bars, c, a, last) -> Optional[Signal]:
        prior_high = rolling_high(c[:-1], self.p.breakout_lookback)
        if prior_high is None or last.close <= prior_high:
            return None
        rv = rvol(bars, self.p.breakout_lookback)
        # Volume is NOT required. The gate only applies if explicitly opted in;
        # otherwise a valid breakout stands on its own regardless of volume.
        if self.p.require_volume_confirmation and rv is not None \
                and rv < self.p.volume_confirm_multiple:
            return None
        breakout = min(1.0, (last.close - prior_high) / a)   # distance in ATRs (primary)
        strength = max(0.05, min(1.0, 0.8 * breakout + self._vol_bonus(rv)))
        return Signal(symbol=symbol, side=Side.BUY, strength=strength,
                      reference_price=last.close, atr=a, kind="momentum",
                      reason=f"breakout>{self.p.breakout_lookback}bar high (RVOL {_fmt(rv)})")

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
        rv = rvol(bars, self.p.zscore_lookback)
        base = min(1.0, abs(z) / 3.0)                        # depth of the dislocation (primary)
        strength = max(0.05, min(1.0, 0.8 * base + self._vol_bonus(rv)))
        return Signal(symbol=symbol, side=Side.BUY, strength=strength,
                      reference_price=last.close, atr=a, kind="reversion",
                      reason=f"oversold (RSI {r:.0f}, z {z:.2f}, RVOL {_fmt(rv)}) in uptrend")

    @staticmethod
    def _vol_bonus(rv: Optional[float]) -> float:
        """A small, optional ranking bonus for heavy volume. Zero when RVOL is
        absent or at/below baseline — volume can only help a rank, never gate."""
        if rv is None or rv <= 1.0:
            return 0.0
        return 0.2 * min(1.0, (rv - 1.0) / 2.0)

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
