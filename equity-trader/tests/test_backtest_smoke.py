import math
from datetime import datetime, timedelta, timezone

from equity_trader.backtest.engine import Backtester
from equity_trader.config.settings import RiskLimits, Settings, StrategyParams, UniverseConfig
from equity_trader.risk.models import Bar
from equity_trader.strategy.momentum_reversion import MomentumReversionStrategy

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def synth(n, base, drift, amp, period, vol=2_000_000):
    """Deterministic price path: linear drift + sine wiggle (no randomness)."""
    bars = []
    prev = base
    for i in range(n):
        c = base + drift * i + amp * math.sin(2 * math.pi * i / period)
        hi = max(prev, c) + amp * 0.3
        lo = min(prev, c) - amp * 0.3
        bars.append(Bar(T0 + timedelta(days=i), open=prev, high=hi, low=lo,
                        close=c, volume=vol))
        prev = c
    return bars


def test_backtester_runs_and_reports():
    n = 120
    settings = Settings(
        starting_equity=100_000,
        risk=RiskLimits(),
        strategy=StrategyParams(trend_lookback=20, breakout_lookback=10, atr_period=14,
                                zscore_lookback=20, volume_confirm_multiple=1.0),
        universe=UniverseConfig(symbols=["SPY", "AAA", "BBB"],
                                min_avg_dollar_volume=0.0, min_price=0.0),
    )
    market = {
        "SPY": synth(n, base=400, drift=0.3, amp=3, period=25),
        "AAA": synth(n, base=100, drift=0.25, amp=4, period=17),
        "BBB": synth(n, base=50, drift=0.1, amp=2, period=11),
    }
    strat = MomentumReversionStrategy(settings.strategy, settings.universe)
    report = Backtester(settings, strat).run(market, benchmark="SPY", warmup=25)

    assert report.periods == n - 25
    assert report.ending_equity > 0
    assert math.isfinite(report.sharpe)
    assert math.isfinite(report.max_drawdown)
    assert isinstance(report.summary(), str)
    assert report.benchmark_symbol == "SPY"
