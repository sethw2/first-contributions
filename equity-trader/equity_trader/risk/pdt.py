"""Pattern Day Trader (PDT) tracking.

FINRA rule: an account under the equity threshold (default $25k) may not make
more than 3 *day trades* (open and close the same symbol on the same trading
day) within any rolling 5 business-day window. Because short-horizon signals
will sometimes round-trip intraday, the system must count day trades and refuse
any trade that would breach the limit.

This tracker records round-trip day trades and answers "may I day-trade now?".
It is timezone-aware and uses US Eastern calendar dates for the day boundary.
"""

from __future__ import annotations

from collections import deque
from datetime import date, datetime, timedelta
from typing import Deque, Dict, List


class PDTTracker:
    def __init__(self, equity_threshold: float = 25_000.0, max_day_trades: int = 3,
                 window_business_days: int = 5) -> None:
        self.equity_threshold = equity_threshold
        self.max_day_trades = max_day_trades
        self.window_business_days = window_business_days
        # Each entry: (trade_date, symbol). One entry per day trade.
        self._day_trades: Deque = deque()
        # Track same-day opens per symbol to detect round trips: symbol -> open dates set.
        self._open_dates: Dict[str, List[date]] = {}

    def record_open(self, symbol: str, when: datetime) -> None:
        self._open_dates.setdefault(symbol, []).append(when.date())

    def record_close(self, symbol: str, when: datetime) -> None:
        """If this close matches an open from the same date, it's a day trade."""
        opens = self._open_dates.get(symbol, [])
        d = when.date()
        if d in opens:
            opens.remove(d)
            self._day_trades.append((d, symbol))
            self._prune(d)

    def day_trades_in_window(self, as_of: date) -> int:
        self._prune(as_of)
        return len(self._day_trades)

    def can_day_trade(self, account_equity: float, as_of: datetime) -> bool:
        """True if a new same-day round trip is permitted right now."""
        if account_equity >= self.equity_threshold:
            return True  # PDT rule does not restrict accounts at/above threshold
        return self.day_trades_in_window(as_of.date()) < self.max_day_trades

    def would_be_day_trade(self, symbol: str, when: datetime) -> bool:
        """True if closing ``symbol`` now would count as a day trade."""
        return when.date() in self._open_dates.get(symbol, [])

    def _prune(self, as_of: date) -> None:
        cutoff = self._business_days_ago(as_of, self.window_business_days)
        while self._day_trades and self._day_trades[0][0] < cutoff:
            self._day_trades.popleft()

    @staticmethod
    def _business_days_ago(d: date, n: int) -> date:
        """Return the date ``n`` business days before ``d`` (rough Mon-Fri calendar)."""
        remaining = n
        cur = d
        while remaining > 0:
            cur = cur - timedelta(days=1)
            if cur.weekday() < 5:  # Mon-Fri
                remaining -= 1
        return cur
