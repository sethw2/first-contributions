"""Risk controls and position sizing.

Responsibilities (to be implemented in later stages):
- Enforce HARD limits (max position size, gross/net exposure, per-name caps,
  daily loss / drawdown kill-switch, order rate limits).
- Size positions given risk budget.

CRITICAL: Risk limits are non-negotiable and MUST NOT be overridable by config.
They apply identically in backtest and live.
Stub only — no implementation yet.
"""
