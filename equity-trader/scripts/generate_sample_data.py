#!/usr/bin/env python3
"""Generate deterministic sample OHLCV CSVs for trying the backtester.

This is SYNTHETIC data for smoke-testing the pipeline only — it is not real
market data and must never be used to judge a strategy's edge. Point the
backtester at a real historical source before drawing any conclusion.

Usage:
    python scripts/generate_sample_data.py --out data_csv --days 400
"""

from __future__ import annotations

import argparse
import csv
import math
import os
from datetime import datetime, timedelta, timezone

SYMBOLS = {
    # symbol: (base_price, daily_drift, wiggle_amplitude, cycle_period)
    "SPY":   (400.0, 0.30, 4.0, 30),
    "QQQ":   (350.0, 0.35, 5.0, 24),
    "AAPL":  (180.0, 0.12, 3.0, 18),
    "MSFT":  (330.0, 0.20, 4.0, 21),
    "NVDA":  (500.0, 0.60, 12.0, 15),
    "XLF":   (38.0,  0.02, 0.6, 27),
}


def gen(symbol, base, drift, amp, period, days):
    t0 = datetime(2024, 1, 2, tzinfo=timezone.utc)
    rows = []
    prev = base
    for i in range(days):
        close = base + drift * i + amp * math.sin(2 * math.pi * i / period)
        high = max(prev, close) + amp * 0.3
        low = min(prev, close) - amp * 0.3
        # Volume spikes on up-days so momentum breakouts get volume confirmation.
        volume = 12_000_000 if close > prev else 5_000_000
        rows.append({
            "timestamp": (t0 + timedelta(days=i)).date().isoformat(),
            "open": round(prev, 2), "high": round(high, 2),
            "low": round(low, 2), "close": round(close, 2),
            "volume": volume,
        })
        prev = close
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data_csv")
    ap.add_argument("--days", type=int, default=400)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    for sym, (base, drift, amp, period) in SYMBOLS.items():
        rows = gen(sym, base, drift, amp, period, args.days)
        path = os.path.join(args.out, f"{sym}.csv")
        with open(path, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=["timestamp", "open", "high", "low", "close", "volume"])
            w.writeheader()
            w.writerows(rows)
        print(f"wrote {path} ({len(rows)} bars)")


if __name__ == "__main__":
    main()
