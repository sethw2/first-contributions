"""Short-horizon US equities trading system.

Top-level package. Submodules are intentionally thin stubs at this stage —
feature code is added in later, explicitly-instructed build stages.

Module map
----------
data       : market/reference data acquisition, storage, and access.
signals    : signal generation. Shared verbatim between backtest and live.
risk       : hard, non-overridable risk limits and position sizing.
execution  : broker-agnostic order routing (Alpaca paper / TradeStation live).
portfolio  : position and account state, P&L, reconciliation.
backtest   : historical simulation that reuses the live signal + risk paths.

Design principles
-----------------
- Correctness, observability, and risk controls over strategy sophistication.
- Broker-agnostic core behind one interface.
- Risk limits are non-negotiable and NOT overridable by config.
- Backtest and live must share the exact same signal and risk code paths.
- Paper-first: real money is gated behind multiple explicit switches.
"""

__version__ = "0.0.0"
