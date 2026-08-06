# Master Prompt: Short-Term Equity Trading System

> **Purpose of this document.** This is a self-contained build prompt to hand to
> Claude Code (or any capable coding agent). Paste the whole thing. It specifies
> *what* to build, the *decisions already made*, the *non-negotiable guardrails*,
> and the *order of operations*. It is opinionated on purpose: a short-term
> trading system succeeds or fails on risk control and honest validation, not on
> the cleverness of its entry signal.

> ⚠️ **Not financial advice.** This describes software. Trading equities involves
> real risk of loss. Nothing here is a recommendation to trade or a promise of
> profit. Run in paper mode until *you* have independently validated behavior.

---

## 0. The one-paragraph brief

Build an automated system that trades liquid US equities and ETFs on a
short-term horizon — **positions held from ~30 minutes up to ~2 weeks**. The
system generates candidate signals from a regime-filtered momentum/mean-reversion
model, sizes positions by volatility, enforces a hard risk budget, executes
through **Alpaca**, and is **paper-trading-only until an explicit, human-gated
promotion to live**. Correctness, observability, and the ability to *stop* the
system instantly matter more than raw returns.

---

## 1. Decisions already made (do not re-litigate these)

These are fixed. Implement them as stated unless you find a concrete technical
blocker, in which case surface it and propose an alternative — don't silently
substitute.

| Area | Decision | Why |
|---|---|---|
| **Broker / execution** | **Alpaca** (Trading API v2) | Commission-free, clean REST + websocket API, and a paper environment byte-compatible with live. |
| **Language / runtime** | **Python 3.11+** | Ecosystem: `pandas`, `numpy`, `alpaca-py`, backtesting libs, mature tooling. |
| **Environments** | **Paper first, always.** Live is a separate, human-unlocked mode. | The single most effective way to avoid catastrophic loss during development. |
| **Universe** | US equities + major ETFs above a **$5M** average-dollar-volume floor (lower-liquidity names allowed given a sub-$100M book) with a $5 min price | Lower-liquidity names are acceptable at small size; the floor still screens out names too thin to exit. Model higher slippage for thinner stocks. No penny stocks. |
| **Trading hours** | **Standard market hours only** (09:30–16:00 ET). No pre/post-market orders. | Avoids thin, gappy extended-hours liquidity. Positions may be held overnight; only *order entry* is restricted to RTH. |
| **Position sizing** | **Operator-decided.** Edge must come from predicting direction, NOT from a sizing scheme. Sizing is kept neutral; signal strength ranks/selects trades but never sets size. | Clean P&L attribution: returns reflect directional accuracy, not bet-sizing cleverness. |
| **Volume** | Used as a **directional input** (relative-volume confirmation + ranking), never as a sizing input. | Breakouts/reversals on heavy participation are more reliable; volume sharpens the *signal*. |
| **Holding horizon** | 30 min (min) to 2 weeks (max), enforced by a **time-based exit** | Matches the brief; caps overnight/weekend gap exposure and prevents "bag-holding." |
| **Leverage** | None by default (cash/RegT long-only to start). Shorting and leverage are opt-in, later phases. | Removes an entire class of blow-up risk from v1. |
| **Data** | Alpaca market data for live; a separate historical source for backtests (Alpaca historical, or Polygon/`yfinance` for research) | Keep backtest and live data paths explicit and comparable. |
| **Scheduling** | Market-calendar-aware loop; never assume the market is open | Trading on stale/closed-market data is a top source of dumb losses. |

### Recommended-but-overridable defaults
You (the operator) can change these; they're my starting recommendations:
- **Starting paper capital:** $100,000 (Alpaca paper default).
- **Per-position risk:** 0.5–1.0% of equity at the stop.
- **Max concurrent positions:** 5–10.
- **Max gross exposure:** 100% of equity (no leverage) in v1.
- **Daily loss circuit breaker:** −3% of equity → flatten and halt for the day.

---

## 2. Non-negotiable guardrails (build these FIRST)

Implement and test the risk layer **before** any strategy logic. A strategy that
can't be stopped or sized is not a feature — it's a liability.

1. **Kill switch.** A single command / file flag / endpoint that (a) cancels all
   open orders, (b) optionally flattens all positions, and (c) prevents any new
   orders until manually cleared. It must work even if the strategy loop is
   wedged. Test it explicitly.
2. **Paper/live guard.** Live trading requires: an explicit config flag, a
   separate credentials profile, AND an interactive confirmation. It must be
   *impossible* to accidentally send a live order while developing. Default to
   paper on any ambiguity.
3. **Position sizing.** Every order is sized from a risk budget (risk-per-trade ×
   equity ÷ per-share stop distance). No naked "buy N shares" calls in strategy
   code — all sizing goes through one `RiskManager`.
4. **Stops on every position.** Both a **hard price stop** (volatility/ATR-based)
   and a **time stop** (auto-exit at the 2-week ceiling, and optionally at
   end-of-day for intraday signals). No position without a defined exit.
5. **Exposure caps.** Enforce max concurrent positions, max per-symbol notional,
   and max gross exposure. Reject orders that would breach them.
6. **Daily loss circuit breaker.** Track realized+unrealized P&L for the session;
   on breach, flatten, halt, and alert.
7. **PDT-rule awareness.** Accounts under $25k are limited to 3 day-trades per
   rolling 5 business days. Because some signals will round-trip same-day, the
   system MUST track day-trade count and refuse trades that would violate PDT
   (or warn loudly). Surface this to the operator.
8. **Idempotent, reconciled orders.** Use client order IDs; on startup, reconcile
   local state against the broker's actual positions/orders before doing
   anything. Never assume local state is truth.
9. **Fail safe, not open.** On any unhandled error, data gap, or lost connection:
   stop sending orders. Silence/uncertainty must never mean "keep trading."

---

## 3. Strategy specification (v1)

Keep v1 simple, explainable, and testable. Alpha comes later; *not losing* comes
first.

**Signal model — regime-filtered momentum / mean-reversion hybrid:**
- **Regime filter:** classify the broad market (e.g., SPY above/below its
  200-period trend, plus a volatility gauge). Only take long momentum signals in
  risk-on regimes; lean to mean-reversion / stand aside in risk-off.
- **Entry (momentum leg):** short-term breakout / relative-strength on the liquid
  universe (e.g., N-day high with a volume confirmation and an ATR-based volatility screen).
- **Entry (mean-reversion leg):** oversold pullback within an established uptrend
  (e.g., RSI/z-score dip that reverts), only in appropriate regime.
- **Exit:** first of — hard stop hit, profit target hit, signal invalidated, or
  time stop (≤ 2 weeks). Exits are as important as entries; specify all of them.
- **Ranking:** when more candidates than open slots, rank by signal strength ×
  liquidity and take the top N.

Every indicator, threshold, and lookback must be a **named config parameter**,
not a magic number buried in code. The strategy interface should make it trivial
to add/swap models later.

---

## 4. Architecture

Build modular, with clean seams so pieces can be tested in isolation:

```
config/          # env-specific YAML: universe, risk limits, thresholds, credentials via env vars (NEVER hardcode secrets)
data/            # market data adapters (live + historical), caching, calendar
strategy/        # signal models behind a common Strategy interface
risk/            # RiskManager: sizing, stops, exposure caps, PDT, circuit breaker
execution/       # broker adapter (Alpaca), order lifecycle, reconciliation, idempotency
backtest/        # event-driven backtester sharing the SAME strategy + risk code as live
engine/          # the orchestration loop: schedule -> data -> signal -> risk -> execute -> log
monitoring/      # structured logging, metrics, alerting, kill switch
tests/           # unit + integration; risk layer coverage is mandatory
```

**Critical design rule:** the backtester and the live engine must run the
*same* strategy and risk code. If they diverge, backtest results are fiction.
Abstract the broker and clock behind interfaces so the only difference between
backtest and live is which adapter is injected.

---

## 5. Backtesting & validation (gate to paper)

- **Event-driven backtester** (bar-by-bar, no look-ahead). Forbid using any data
  point that wouldn't have been available at decision time.
- **Realistic cost model:** commission (Alpaca = $0, but model it anyway), plus
  **slippage** and spread assumptions. Optimistic fills are how backtests lie.
- **Walk-forward / out-of-sample:** tune on one window, validate on the next,
  never on the same data. Report in-sample vs out-of-sample degradation.
- **Metrics:** total & annualized return, max drawdown, Sharpe/Sortino, win rate,
  average win/loss, exposure, turnover, and P&L *after* costs.
- **Sanity checks:** shuffle/label tests, a "random-entry" baseline, and a
  buy-and-hold SPY benchmark. If the strategy can't beat buy-and-hold on a
  risk-adjusted, post-cost basis, say so plainly.

---

## 6. Operational plan (the promotion ladder)

Move one rung at a time. Do not skip.

1. **Build + unit test** the risk layer and execution adapter (paper creds).
2. **Backtest** the strategy across multiple regimes and out-of-sample windows.
3. **Paper trade live** for a defined, pre-committed period (e.g., ≥ 20 trading
   days) with full logging and daily P&L review. Compare paper results to
   backtest expectations — large divergence means a bug or a bad model.
4. **Human-gated live promotion**, if and only if paper results and the operator
   both approve. Start with the smallest meaningful capital and the tightest
   limits, then scale slowly.

At every rung: structured logs of every decision (why entered, size rationale,
stop, exit reason), a daily summary, and alerts on breaches and errors.

---

## 7. What "done" looks like for v1

- Risk layer + kill switch implemented and unit-tested.
- Alpaca paper execution with startup reconciliation and idempotent orders.
- One working strategy behind the `Strategy` interface, fully parameterized.
- Event-driven backtester sharing live code, with a post-cost report and a
  buy-and-hold benchmark.
- Market-calendar-aware engine loop that runs a full paper session unattended
  without sending a single unintended or out-of-hours order.
- README documenting setup, the paper→live ladder, every risk limit, and how to
  hit the kill switch.

---

## 8. Guidance for the coding agent (how to work through this)

- **Order of build = order of safety.** Guardrails (§2) and the risk layer
  before strategy. Backtester before live wiring. Never wire live credentials
  until paper is proven.
- **Secrets via environment variables only.** Never commit keys. Provide a
  `.env.example`; keep real creds out of git.
- **Small, tested increments.** Each module lands with tests. The risk module
  gets adversarial tests (bad prices, disconnects, partial fills, PDT edges).
- **When you must assume, default to the safe/conservative choice** and state the
  assumption in your summary. Ambiguity resolves toward *not trading*.
- **Flag genuine forks to the operator** rather than guessing on anything that
  affects real money (live promotion, leverage, universe expansion).
- **Be honest in reporting.** If the edge is weak, if a test is skipped, if
  results are unproven — say so directly. A trading system built on flattering
  summaries is dangerous.

---

*This prompt is a starting specification, not a guarantee. Validate everything in
paper. You are responsible for any capital you put at risk.*
