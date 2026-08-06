"""Short-term equity trading system.

A paper-first, risk-controlled automated trader for liquid US equities and ETFs
on a 30-minute to 2-week horizon. See the repository README and the master
prompt (``equity-trading-app-prompt.md``) for the full specification.

The build order mirrors the safety order: the risk layer and guardrails come
first, then execution, strategy, backtesting, and finally the live engine.
"""

__version__ = "0.1.0"
