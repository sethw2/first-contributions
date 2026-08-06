from datetime import datetime, timedelta, timezone

from equity_trader.config.settings import RiskLimits, Settings, StrategyParams, UniverseConfig
from equity_trader.engine.core import TradingEngine
from equity_trader.execution.paper_sim import PaperSimBroker
from equity_trader.risk.kill_switch import KillSwitch
from equity_trader.risk.manager import RiskManager
from equity_trader.risk.models import Bar
from equity_trader.strategy.momentum_reversion import MomentumReversionStrategy

T0 = datetime(2026, 8, 3, 15, tzinfo=timezone.utc)


def mk_bars(closes, vol=1_000_000):
    out = []
    prev = closes[0]
    for i, c in enumerate(closes):
        out.append(Bar(T0 + timedelta(minutes=30 * i), open=prev,
                       high=max(prev, c) + 0.2, low=min(prev, c) - 0.2,
                       close=c, volume=vol))
        prev = c
    return out


def build_engine(tmp_path):
    settings = Settings(
        risk=RiskLimits(allow_shorting=False),
        strategy=StrategyParams(trend_lookback=5, breakout_lookback=3, atr_period=3,
                                volume_confirm_multiple=1.0, max_new_positions_per_cycle=3),
        universe=UniverseConfig(symbols=["SPY", "AAA"], min_avg_dollar_volume=0.0, min_price=0.0),
    )
    broker = PaperSimBroker(starting_cash=100_000, slippage_bps=0.0)
    risk = RiskManager(settings.risk, KillSwitch(flag_path=str(tmp_path / "KILL")))
    strat = MomentumReversionStrategy(settings.strategy, settings.universe)
    engine = TradingEngine(settings, broker, strat, risk)
    engine.startup()
    return engine, broker


# Need >= 20 bars for the strategy's average-dollar-volume liquidity screen.
SPY_UP = [100 + i for i in range(22)]      # steady uptrend -> risk_on regime
AAA_BREAKOUT = [10.0] * 21 + [12.0]        # flat, then a breakout on the last bar


def test_momentum_entry_then_stop_out(tmp_path):
    engine, broker = build_engine(tmp_path)
    spy = mk_bars(SPY_UP)
    aaa = mk_bars(AAA_BREAKOUT)
    last_i = len(SPY_UP) - 1

    engine.run_cycle({"SPY": spy, "AAA": aaa}, T0 + timedelta(minutes=30 * last_i))
    assert "AAA" in engine.positions, "expected a momentum entry on the breakout"
    entry = engine.positions["AAA"]
    assert entry.qty > 0 and entry.stop_price < entry.avg_entry_price

    # Next bar: AAA collapses well below the hard stop -> forced exit.
    spy2 = spy + [Bar(T0 + timedelta(minutes=30 * (last_i + 1)), open=121, high=122,
                      low=120, close=122, volume=1_000_000)]
    aaa2 = aaa + [Bar(T0 + timedelta(minutes=30 * (last_i + 1)), open=12, high=12,
                      low=1, close=1.0, volume=1_000_000)]
    engine.run_cycle({"SPY": spy2, "AAA": aaa2}, T0 + timedelta(minutes=30 * (last_i + 1)))
    assert "AAA" not in engine.positions, "expected a hard-stop exit"


def test_kill_switch_halts_cycle(tmp_path):
    engine, broker = build_engine(tmp_path)
    engine.risk.kill_switch.trip("test halt", write_file=False)
    engine.run_cycle({"SPY": mk_bars(SPY_UP), "AAA": mk_bars(AAA_BREAKOUT)},
                     T0 + timedelta(minutes=30 * (len(SPY_UP) - 1)))
    assert engine.positions == {}, "no entries allowed while kill switch is tripped"
