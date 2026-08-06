# Equity Trader

A paper-first, risk-controlled automated trading system for liquid US equities
and ETFs on a **short-term horizon (30 minutes to 2 weeks)**. Built from the
specification in [`../equity-trading-app-prompt.md`](../equity-trading-app-prompt.md).

> ⚠️ **Not financial advice. Trades real money only when you explicitly enable
> live mode.** Equities trading carries real risk of loss. This is software, not
> a recommendation or a promise of profit. Validate everything in paper first.

The design philosophy, in one line: **correctness, observability, and the
ability to stop instantly matter more than raw returns.** The risk layer was
built and tested before any strategy logic.

---

## What's here

```
equity_trader/
  config/       settings, RiskLimits, default.yaml   (secrets come from env ONLY)
  data/         market-calendar awareness + data providers (CSV, Alpaca)
  strategy/     Strategy interface, indicators, regime filter, v1 hybrid model
  risk/         RiskManager, kill switch, PDT tracker, domain models  ← built first
  execution/    Broker interface, PaperSimBroker, Alpaca adapter, reconciliation
  backtest/     event-driven backtester (shares live code), costs, metrics
  engine/       shared decision core, clocks, live loop
  monitoring/   structured logging, alerting
tests/          unit + integration; the risk layer is covered adversarially
scripts/        sample-data generator
run.py          CLI entrypoint (backtest / paper / live / kill)
```

**Key design rule:** the backtester and the live engine run the *same* strategy
and risk code. The only difference between backtest, paper, and live is which
`Broker` and `Clock` are injected. If they diverged, backtest results would be
fiction.

## The guardrails (built first, tested hardest)

| Guardrail | Where |
|---|---|
| Kill switch (file-flag, works even if the loop is wedged) | `risk/kill_switch.py` |
| Volatility-based position sizing (single gate) | `risk/manager.py` |
| Hard price stop + time stop on every position | `risk/models.py`, `engine/core.py` |
| Exposure caps (positions, per-symbol notional, gross) | `risk/manager.py` |
| Daily loss circuit breaker (flatten & halt) | `risk/manager.py` |
| PDT-rule tracking (< $25k → 3 day-trades / 5 days) | `risk/pdt.py` |
| Idempotent orders + startup reconciliation | `execution/` |
| Fail-safe: any error/data gap → stop trading | `engine/loop.py` |
| Paper/live guard (live needs explicit flag + confirm) | `execution/alpaca_broker.py` |

## Quick start

```bash
# 1. (optional) install extras for live trading / calendars
pip install -r requirements.txt

# 2. Run the tests — the risk layer is the important part
python -m pytest -q

# 3. Try the backtester on generated SAMPLE data (synthetic, not real!)
python scripts/generate_sample_data.py --out data_csv --days 400
python run.py backtest --data-dir data_csv --benchmark SPY
```

The backtest prints a report including a **buy-and-hold benchmark** and refuses
to flatter itself: if the strategy doesn't beat buy-and-hold after costs, the
report says so in plain language.

## The promotion ladder (do not skip rungs)

1. **Build + unit test** the risk layer and execution adapter. ✅ (this scaffold)
2. **Backtest** across regimes and out-of-sample windows on *real* data.
3. **Paper trade** live for a pre-committed period (≥ ~20 trading days), and
   compare paper results to backtest expectations.
4. **Human-gated live** promotion — smallest capital, tightest limits, scale slowly.

```bash
# Paper trading (needs Alpaca PAPER keys in the environment)
cp .env.example .env    # then edit; NEVER commit real keys
export $(grep -v '^#' .env | xargs)
python run.py paper --timeframe 30Min --poll 60

# Live trading is deliberately hard to start:
python run.py live --i-understand-live   # also prompts for interactive confirmation

# Stop everything, now:
python run.py kill --reason "manual halt"
#   ...or from any shell:  touch KILL_SWITCH
```

## Configuration

Edit `equity_trader/config/default.yaml`. Every risk limit, universe rule, and
strategy threshold is a named parameter — no magic numbers in code. Secrets
(`ALPACA_API_KEY`, `ALPACA_API_SECRET`) are read from the **environment only**
and never from YAML.

Defaults are conservative on purpose: 0.75% risk per trade, ≤ 8 positions, no
leverage, long-only, 20% max per-symbol notional, −3% daily circuit breaker,
2-week max hold.

Operator-set behavior baked in per guidance:

- **Standard market hours only** (`regular_hours_only: true`). Orders are sent
  only during the 9:30–16:00 ET regular session — no pre/post-market. Positions
  may still be *held* overnight up to the time stop; a stop breached overnight is
  acted on at the next open (an accepted consequence of RTH-only trading).
- **Lower-liquidity names allowed.** The average-dollar-volume floor is $5M
  (down from $20M): with a sub-$100M book we won't move these names. Backtest
  slippage was raised to 5 bps to keep results honest for thinner stocks.
- **Edge comes from direction, not sizing.** Signal strength — including the new
  relative-volume (RVOL) input — only *ranks and selects* trades. It never
  changes position size. The sizing scheme itself is an operator decision (see
  below).

## Honest limitations (v1)

This is a **scaffold**, not a validated money-maker. Specifically:

- The sample data is synthetic — it proves the plumbing, not an edge. Backtest
  on real historical data before drawing any conclusion.
- The v1 strategy is intentionally simple and explainable; it has **not** been
  shown to have positive expectancy.
- Intraday fill modeling is close-based; a real deployment needs bar-level or
  tick-level fill logic and live slippage measurement.
- Walk-forward/out-of-sample tooling is described in the spec but left as the
  next step — do that before paper, and paper before live.

Read the master prompt for the full rationale and the rungs still ahead.
