"""Clock abstraction.

The engine reads time only through a Clock, so a backtest can drive a simulated
clock while live trading uses the wall clock. This keeps the two paths identical.
"""

from __future__ import annotations

import abc
from datetime import datetime, timezone


class Clock(abc.ABC):
    @abc.abstractmethod
    def now(self) -> datetime: ...


class RealClock(Clock):
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class SimClock(Clock):
    """A clock the backtester advances bar by bar."""

    def __init__(self, start: datetime) -> None:
        self._now = start

    def now(self) -> datetime:
        return self._now

    def set(self, when: datetime) -> None:
        self._now = when
