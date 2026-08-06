from datetime import datetime, timedelta, timezone

from equity_trader.config.settings import StrategyParams, UniverseConfig
from equity_trader.risk.models import Bar
from equity_trader.strategy.momentum_reversion import MomentumReversionStrategy

T0 = datetime(2026, 8, 3, 15, tzinfo=timezone.utc)


def mk_bars(closes, volumes):
    out = []
    prev = closes[0]
    for i, (c, v) in enumerate(zip(closes, volumes)):
        out.append(Bar(T0 + timedelta(minutes=30 * i), open=prev,
                       high=max(prev, c) + 0.2, low=min(prev, c) - 0.2,
                       close=c, volume=v))
        prev = c
    return out


def _params(**kw):
    base = dict(trend_lookback=5, breakout_lookback=3, atr_period=3)
    base.update(kw)
    return StrategyParams(**base)


def _universe():
    return UniverseConfig(symbols=["SPY", "AAA"], min_avg_dollar_volume=0.0, min_price=0.0)


SPY_UP = [100 + i for i in range(22)]
AAA_BREAKOUT = [10.0] * 21 + [12.0]
# Volume that DROPS on the breakout bar -> RVOL well below 1.0 (a thin breakout).
LOW_VOL = [1_000_000] * 21 + [100_000]


def test_low_volume_breakout_still_signals_by_default():
    """Volume is not required: a valid breakout signals even on thin volume."""
    strat = MomentumReversionStrategy(_params(), _universe())
    market = {"SPY": mk_bars(SPY_UP, [1_000_000] * 22),
              "AAA": mk_bars(AAA_BREAKOUT, LOW_VOL)}
    signals = strat.generate_signals(market, T0, open_symbols=[])
    assert any(s.symbol == "AAA" and s.kind == "momentum" for s in signals)


def test_opt_in_gate_filters_thin_breakout():
    """With the gate explicitly enabled, the thin breakout is rejected."""
    strat = MomentumReversionStrategy(
        _params(require_volume_confirmation=True, volume_confirm_multiple=1.2), _universe())
    market = {"SPY": mk_bars(SPY_UP, [1_000_000] * 22),
              "AAA": mk_bars(AAA_BREAKOUT, LOW_VOL)}
    signals = strat.generate_signals(market, T0, open_symbols=[])
    assert not any(s.symbol == "AAA" for s in signals)


def test_heavy_volume_ranks_higher_but_is_not_required():
    """RVOL only nudges the ranking score; it never gates."""
    strat = MomentumReversionStrategy(_params(), _universe())
    heavy = {"SPY": mk_bars(SPY_UP, [1_000_000] * 22),
             "AAA": mk_bars(AAA_BREAKOUT, [1_000_000] * 21 + [4_000_000])}
    thin = {"SPY": mk_bars(SPY_UP, [1_000_000] * 22),
            "AAA": mk_bars(AAA_BREAKOUT, LOW_VOL)}
    s_heavy = strat.generate_signals(heavy, T0, [])[0]
    s_thin = strat.generate_signals(thin, T0, [])[0]
    assert s_heavy.strength > s_thin.strength  # heavy volume ranks higher
    assert s_thin.strength > 0                 # but thin still produces a signal
