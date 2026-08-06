"""Performance metrics, pure-Python.

All returns are computed AFTER costs (the equity curve already reflects
slippage/commission). Includes a buy-and-hold benchmark so results are always
reported against the honest alternative of doing nothing clever.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Sequence


@dataclass
class BacktestReport:
    starting_equity: float
    ending_equity: float
    total_return: float
    max_drawdown: float
    sharpe: float
    sortino: float
    num_trades: int
    periods: int
    benchmark_return: float = 0.0
    benchmark_symbol: str = ""
    excess_return: float = 0.0
    notes: List[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            "=== Backtest report ===",
            f"periods:            {self.periods}",
            f"starting equity:    {self.starting_equity:,.2f}",
            f"ending equity:      {self.ending_equity:,.2f}",
            f"total return:       {self.total_return:+.2%}",
            f"max drawdown:       {self.max_drawdown:.2%}",
            f"Sharpe (ann.):      {self.sharpe:.2f}",
            f"Sortino (ann.):     {self.sortino:.2f}",
            f"trades:             {self.num_trades}",
            f"buy&hold {self.benchmark_symbol or 'benchmark'}: {self.benchmark_return:+.2%}",
            f"excess vs B&H:      {self.excess_return:+.2%}",
        ]
        lines += [f"note: {n}" for n in self.notes]
        return "\n".join(lines)


def _returns(equity_curve: Sequence[float]) -> List[float]:
    out = []
    for i in range(1, len(equity_curve)):
        prev = equity_curve[i - 1]
        out.append((equity_curve[i] - prev) / prev if prev else 0.0)
    return out


def max_drawdown(equity_curve: Sequence[float]) -> float:
    peak = equity_curve[0] if equity_curve else 0.0
    mdd = 0.0
    for v in equity_curve:
        peak = max(peak, v)
        if peak > 0:
            mdd = min(mdd, (v - peak) / peak)
    return mdd


def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _std(xs: Sequence[float], downside: bool = False) -> float:
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    sample = [min(0.0, x - m) if downside else (x - m) for x in xs]
    var = sum(s * s for s in sample) / (len(xs) - 1)
    return var ** 0.5


def sharpe(equity_curve: Sequence[float], periods_per_year: int = 252) -> float:
    r = _returns(equity_curve)
    sd = _std(r)
    if sd == 0:
        return 0.0
    return (_mean(r) / sd) * (periods_per_year ** 0.5)


def sortino(equity_curve: Sequence[float], periods_per_year: int = 252) -> float:
    r = _returns(equity_curve)
    dd = _std(r, downside=True)
    if dd == 0:
        return 0.0
    return (_mean(r) / dd) * (periods_per_year ** 0.5)


def buy_and_hold_return(prices: Sequence[float]) -> float:
    if len(prices) < 2 or prices[0] == 0:
        return 0.0
    return (prices[-1] - prices[0]) / prices[0]


def build_report(equity_curve: List[float], num_trades: int,
                 benchmark_prices: Sequence[float], benchmark_symbol: str,
                 periods_per_year: int = 252) -> BacktestReport:
    start = equity_curve[0]
    end = equity_curve[-1]
    total = (end - start) / start if start else 0.0
    bh = buy_and_hold_return(benchmark_prices)
    report = BacktestReport(
        starting_equity=start,
        ending_equity=end,
        total_return=total,
        max_drawdown=max_drawdown(equity_curve),
        sharpe=sharpe(equity_curve, periods_per_year),
        sortino=sortino(equity_curve, periods_per_year),
        num_trades=num_trades,
        periods=len(equity_curve),
        benchmark_return=bh,
        benchmark_symbol=benchmark_symbol,
        excess_return=total - bh,
    )
    if total <= bh:
        report.notes.append(
            "Strategy did NOT beat buy-and-hold after costs. Do not deploy on this evidence."
        )
    return report
