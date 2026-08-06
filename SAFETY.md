# SAFETY

> **Status: stub.** The controls below describe intended behavior. Enforcement
> is implemented in later stages. Until then, treat everything as paper-only.

This system can place real orders with real money. The rules here exist to make
that **hard to do by accident** and **impossible to do quietly**.

## Non-negotiables

1. **Paper is the default, everywhere.** Every entry point defaults to
   `TradingMode.PAPER`. Live mode is never implied.
2. **Risk limits are not overridable by config.** Position size, exposure,
   per-name caps, daily-loss / drawdown kill-switch, and order-rate limits are
   enforced in code and apply identically in backtest and live. No config value
   can loosen or disable them.
3. **Backtest and live share the same signal and risk code.** No forked
   "backtest-only" path.

## The live-trading gate (multiple independent switches)

Real money requires **all** of the following, in different places, so no single
change can arm live trading:

- [ ] `EQUITIES_ALLOW_LIVE=1` in the environment (not in committed config).
- [ ] An explicit runtime `arm_live_trading()` call — code, not configuration.
- [ ] Per-session confirmation (interactive / second factor).
- [ ] A broker configured with **live** (not paper/sim) endpoints and credentials.

If any switch is missing, the system must refuse to construct a live broker and
fall back to paper.

## Secrets

- All secrets come from the environment (`.env` in dev). `.env` is gitignored.
- Never commit keys, tokens, or account IDs. See `.env.example` for names only.

## Incident expectations (to be built out)

- Kill-switch that flattens or halts on breach of daily loss / drawdown limits.
- Reconciliation of internal state against broker-reported state before trading.
- Structured, auditable logging of every order decision and risk check.

---

_Update this document as each control is actually implemented. A checkbox here
is a promise the code must keep._
