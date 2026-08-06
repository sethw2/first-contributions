"""Live/paper orchestration loop.

Wraps the shared ``TradingEngine`` with a market-calendar-aware schedule. It:
- refuses to trade when the market is closed (never acts on stale data),
- polls the kill switch every tick,
- fetches fresh bars for the universe each cycle,
- shuts down cleanly on SIGINT/SIGTERM.

This module only *schedules*; all trading decisions live in ``TradingEngine``.
"""

from __future__ import annotations

import logging
import signal
import time
from typing import Dict, List

from ..config.settings import Settings
from ..data.calendar import is_market_open
from ..data.market_data import MarketDataProvider
from ..risk.models import Bar
from .clock import Clock, RealClock
from .core import TradingEngine

log = logging.getLogger("equity_trader.loop")


class LiveLoop:
    def __init__(self, settings: Settings, engine: TradingEngine,
                 data: MarketDataProvider, poll_seconds: int = 60,
                 history_bars: int = 250, clock: Clock | None = None) -> None:
        self.settings = settings
        self.engine = engine
        self.data = data
        self.poll_seconds = poll_seconds
        self.history_bars = history_bars
        self.clock = clock or RealClock()
        self._running = False

    def _install_signal_handlers(self) -> None:
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, lambda *_: self.stop())
            except (ValueError, OSError):  # e.g. not in main thread
                pass

    def stop(self) -> None:
        log.info("shutdown requested")
        self._running = False

    def _snapshot(self) -> Dict[str, List[Bar]]:
        market: Dict[str, List[Bar]] = {}
        for symbol in self.settings.universe.symbols:
            try:
                market[symbol] = self.data.get_bars(symbol, self.history_bars)
            except Exception as exc:  # data gap for one name must not trade blind
                log.warning("data fetch failed for %s: %s", symbol, exc)
        return market

    def run(self) -> None:
        self._install_signal_handlers()
        self.engine.startup()
        self._running = True
        log.info("live loop started (poll=%ss)", self.poll_seconds)

        while self._running:
            now = self.clock.now()
            if self.engine.risk.kill_switch.is_tripped:
                log.error("kill switch tripped; halting loop")
                self.engine.broker.cancel_all_orders()
                break
            # Standard-market-hours-only: never send orders outside the 9:30-16:00
            # ET regular session. (Positions may still be *held* overnight up to
            # the 2-week time stop; we simply do not trade until the market reopens.)
            if self.settings.regular_hours_only and not is_market_open(now):
                log.debug("market closed at %s; idling", now.isoformat())
                time.sleep(self.poll_seconds)
                continue
            try:
                self.engine.run_cycle(self._snapshot(), now)
            except Exception:  # fail safe: never keep trading through an error
                log.exception("cycle error; halting for safety")
                self.engine.broker.cancel_all_orders()
                break
            time.sleep(self.poll_seconds)

        log.info("live loop stopped")
