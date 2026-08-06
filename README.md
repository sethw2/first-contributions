# equities — short-horizon US equities trading system

> **Status: scaffold only.** No trading logic is implemented yet. This stage
> sets up structure, tooling, and safety guardrails. Feature code lands in
> later, explicitly-instructed stages.

A Python system for short-horizon US equities (roughly 30-minute to 2-week
holding periods). **Paper-first**; real money is gated behind multiple explicit
switches. See [SAFETY.md](SAFETY.md).

## Principles

- Correctness, observability, and risk controls over strategy sophistication.
- Broker-agnostic core: `AlpacaBroker` (paper, the dev default) and
  `TradeStationBroker` (REST/OAuth, the live path) behind one interface.
- Risk limits are non-negotiable and **not** overridable by config.
- Backtest and live share the **exact same** signal and risk code paths.

## Layout

```
src/equities/
  data/        market/reference data acquisition, storage, access
  signals/     signal generation (shared verbatim by backtest and live)
  risk/        hard, non-overridable risk limits and position sizing
  execution/   broker-agnostic order routing (Alpaca / TradeStation)
  portfolio/   positions, cash, P&L, reconciliation
  backtest/    historical simulation reusing the live signal + risk paths
  config.py    configuration and the multi-switch live-trading gate
tests/         test suite
```

## Setup

Using **uv** (recommended):

```bash
uv sync --extra dev
```

Or a plain **venv**:

```bash
make setup      # python -m venv .venv + pip install
```

Then:

```bash
cp .env.example .env   # fill in secrets; .env is gitignored
make check             # lint + typecheck + test
```

## Tooling

- **uv** (or venv + `requirements*.txt`) for dependencies
- **ruff** for lint + format
- **mypy** for type checking
- **pytest** for tests

Common targets: `make lint`, `make fmt`, `make typecheck`, `make test`, `make check`.

## Safety

Real-money trading requires every switch described in [SAFETY.md](SAFETY.md).
The default mode is paper, everywhere.

---

_This repository was bootstrapped from a fork of the `first-contributions`
tutorial. The original tutorial README is preserved in git history._
