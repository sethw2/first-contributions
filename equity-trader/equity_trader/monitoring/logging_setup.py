"""Structured logging setup.

Every decision the engine makes is logged with a rationale (why entered, size,
stop, exit reason) so a session can be audited after the fact. Logs go to both
stdout and a dated file under ``log_dir``.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone


def setup_logging(log_dir: str = "./logs", level: int = logging.INFO) -> logging.Logger:
    os.makedirs(log_dir, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    log_path = os.path.join(log_dir, f"trading-{stamp}.log")

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    root = logging.getLogger("equity_trader")
    root.setLevel(level)
    root.handlers.clear()

    stream = logging.StreamHandler()
    stream.setFormatter(fmt)
    root.addHandler(stream)

    file_handler = logging.FileHandler(log_path)
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    root.propagate = False
    return root
