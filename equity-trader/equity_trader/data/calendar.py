"""Market calendar awareness.

Never assume the market is open. Uses ``pandas_market_calendars`` when
available for holiday-accurate hours; otherwise falls back to a conservative
regular-hours check (weekdays, 09:30-16:00 US/Eastern). The fallback errs
toward "closed" on uncertainty.
"""

from __future__ import annotations

from datetime import datetime, time, timezone


def _to_eastern(dt: datetime):
    try:
        from zoneinfo import ZoneInfo
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(ZoneInfo("America/New_York"))
    except Exception:
        return dt


def is_market_open(now: datetime) -> bool:
    """True if the US equity market is in regular session at ``now``."""
    try:
        import pandas_market_calendars as mcal  # optional
        import pandas as pd
        nyse = mcal.get_calendar("XNYS")
        et = _to_eastern(now)
        sched = nyse.schedule(start_date=et.date(), end_date=et.date())
        if sched.empty:
            return False
        ts = pd.Timestamp(now if now.tzinfo else now.replace(tzinfo=timezone.utc))
        open_ts = sched.iloc[0]["market_open"]
        close_ts = sched.iloc[0]["market_close"]
        return open_ts <= ts <= close_ts
    except Exception:
        return _fallback_is_open(now)


def _fallback_is_open(now: datetime) -> bool:
    et = _to_eastern(now)
    if et.weekday() >= 5:  # Sat/Sun
        return False
    return time(9, 30) <= et.time() <= time(16, 0)


def minutes_until_close(now: datetime) -> float:
    """Rough minutes until 16:00 ET; 0 if already closed."""
    if not is_market_open(now):
        return 0.0
    et = _to_eastern(now)
    close = et.replace(hour=16, minute=0, second=0, microsecond=0)
    return max(0.0, (close - et).total_seconds() / 60.0)
