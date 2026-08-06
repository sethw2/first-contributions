"""Configuration and the live-trading gate (stub).

This module documents the *shape* of configuration and the multi-switch gate
that must all be satisfied before any real-money order can be placed. It does
NOT implement broker connectivity or trading logic yet.

Design notes for later stages
------------------------------
- Secrets come from the environment (.env in dev), never committed. See
  .env.example for the variable names.
- `TradingMode.PAPER` is the default everywhere. Real money requires ALL of the
  independent switches below to be explicitly set — no single flag can enable
  live trading, and risk limits (see equities.risk) are enforced regardless of
  configuration.
"""

from __future__ import annotations

import enum


class TradingMode(enum.Enum):
    """Execution mode. Paper is the development default."""

    PAPER = "paper"
    LIVE = "live"


# The independent switches that must ALL be true to arm real-money trading.
# Intentionally more than one, in different places (env + explicit code call +
# per-session confirmation), so live trading can never be enabled by accident.
# Wired up in a later stage.
LIVE_TRADING_SWITCHES = (
    "EQUITIES_ALLOW_LIVE",        # environment variable, must equal "1"
    "arm_live_trading() called",  # explicit runtime call, not config
    "per-session confirmation",   # interactive/second-factor confirmation
)

DEFAULT_MODE = TradingMode.PAPER

# TODO(stage: config): implement a validated settings loader (e.g. pydantic)
# that reads the .env.example variables and refuses to construct a live broker
# unless every switch in LIVE_TRADING_SWITCHES is satisfied.
