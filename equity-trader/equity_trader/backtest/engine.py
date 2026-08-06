"""Event-driven backtester.

Reuses the live ``TradingEngine``, ``RiskManager``, and strategy verbatim — the
only substitutions are a ``PaperSimBroker`` and a ``SimClock``. If this diverged
from live, the results would be fiction. No look-ahead: at bar ``i`` the engine
only ever sees ``bars[: i + 1]``.

The daily loss circuit breaker is re-anchored at each new calendar day to mirror
how it behaves in live session-by-session trading.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from ..config.settings import Settings
from ..engine.clock import SimClock
from ..engine.core import TradingEngine
from ..risk.kill_switch import KillSwitch
from ..risk.manager import RiskManager
from ..risk.models import Bar
from ..strategy.base import Strategy
from .costs import CostModel
from .metrics import BacktestReport, build_report


class Backtester:
    def __init__(self, settings: Settings, strategy: Strategy,
                 cost_model: Optional[CostModel] = None) -> None:
        self.settings = settings
        self.strategy = strategy
        self.cost_model = cost_model or CostModel()

    def run(self, market_full: Dict[str, List[Bar]], benchmark: str = "SPY",
            warmup: Optional[int] = None) -> BacktestReport:
        if benchmark not in market_full:
            raise ValueError(f"benchmark {benchmark!r} not in market data")

        timeline = [b.timestamp for b in market_full[benchmark]]
        n = min(len(bars) for bars in market_full.values())
        warmup = warmup if warmup is not None else (self.settings.strategy.trend_lookback + 1)
        if warmup >= n:
            raise ValueError(f"not enough history: warmup={warmup} >= n={n}")

        broker = self.cost_model.build_broker(self.settings.starting_equity)
        # A kill switch pointed at a path that does not exist -> never tripped in backtest.
        kill = KillSwitch(flag_path="./.backtest_no_kill_flag")
        risk = RiskManager(self.settings.risk, kill)
        engine = TradingEngine(self.settings, broker, self.strategy, risk)
        clock = SimClock(start=timeline[warmup])
        engine.startup()

        equity_curve: List[float] = []
        prev_day = None
        for i in range(warmup, n):
            now = timeline[i]
            clock.set(now)
            if prev_day != now.date():
                risk.start_session(broker.get_account())  # daily circuit-breaker anchor
                prev_day = now.date()
            market_slice = {s: bars[: i + 1] for s, bars in market_full.items() if len(bars) > i}
            engine.run_cycle(market_slice, now)
            equity_curve.append(broker.get_account().equity)

        benchmark_prices = [b.close for b in market_full[benchmark]][warmup:n]
        return build_report(
            equity_curve=equity_curve,
            num_trades=broker.filled_order_count,
            benchmark_prices=benchmark_prices,
            benchmark_symbol=benchmark,
        )
