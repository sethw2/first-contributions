"""Order execution — broker-agnostic core.

Responsibilities (to be implemented in later stages):
- Define one Broker interface used by all callers.
- AlpacaBroker  : paper trading, the development default.
- TradeStationBroker : REST/OAuth, the live-money path.
- Idempotent order submission, fills, cancels, and status polling.

CRITICAL: Live money is gated behind multiple explicit switches (see config
and SAFETY.md). Paper is always the default.
Stub only — no implementation yet.
"""
