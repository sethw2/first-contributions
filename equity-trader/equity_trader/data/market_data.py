"""Market data providers.

A common interface with two adapters:
- ``AlpacaDataProvider``   : live/recent bars (lazy ``alpaca-py`` import).
- ``CsvDataProvider``      : historical bars from CSV, for backtests/tests.

Bars are always returned oldest-first as lists of ``Bar`` so the pure-Python
indicators can consume them directly.
"""

from __future__ import annotations

import abc
import csv
from datetime import datetime, timezone
from typing import Dict, List, Optional

from ..risk.models import Bar


class MarketDataProvider(abc.ABC):
    @abc.abstractmethod
    def get_bars(self, symbol: str, limit: int) -> List[Bar]:
        """Return up to ``limit`` most-recent bars, oldest first."""


class CsvDataProvider(MarketDataProvider):
    """Loads bars from ``{dir}/{symbol}.csv`` with columns:
    timestamp,open,high,low,close,volume (timestamp ISO-8601).
    """

    def __init__(self, directory: str) -> None:
        self.directory = directory
        self._cache: Dict[str, List[Bar]] = {}

    def load(self, symbol: str) -> List[Bar]:
        if symbol in self._cache:
            return self._cache[symbol]
        path = f"{self.directory}/{symbol}.csv"
        bars: List[Bar] = []
        with open(path, newline="") as fh:
            for row in csv.DictReader(fh):
                bars.append(Bar(
                    timestamp=_parse_ts(row["timestamp"]),
                    open=float(row["open"]), high=float(row["high"]),
                    low=float(row["low"]), close=float(row["close"]),
                    volume=float(row["volume"]),
                ))
        bars.sort(key=lambda b: b.timestamp)
        self._cache[symbol] = bars
        return bars

    def get_bars(self, symbol: str, limit: int) -> List[Bar]:
        return self.load(symbol)[-limit:]


class AlpacaDataProvider(MarketDataProvider):
    def __init__(self, api_key: str, api_secret: str, feed: str = "iex",
                 timeframe: str = "1Day") -> None:
        try:
            from alpaca.data.historical import StockHistoricalDataClient  # lazy
        except ImportError as exc:  # pragma: no cover
            raise ImportError("alpaca-py required: pip install alpaca-py") from exc
        self._client = StockHistoricalDataClient(api_key, api_secret)
        self._feed = feed
        self._timeframe = timeframe

    def get_bars(self, symbol: str, limit: int) -> List[Bar]:  # pragma: no cover - network
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
        tf = TimeFrame(1, TimeFrameUnit.Day) if self._timeframe == "1Day" \
            else TimeFrame(30, TimeFrameUnit.Minute)
        req = StockBarsRequest(symbol_or_symbols=symbol, timeframe=tf, limit=limit)
        resp = self._client.get_stock_bars(req)
        out: List[Bar] = []
        for b in resp.data.get(symbol, []):
            out.append(Bar(timestamp=b.timestamp, open=b.open, high=b.high,
                           low=b.low, close=b.close, volume=b.volume))
        return out


def _parse_ts(value: str) -> datetime:
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        dt = datetime.strptime(value, "%Y-%m-%d")
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
