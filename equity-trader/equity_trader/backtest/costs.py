"""Cost model for backtests.

Optimistic fills are how backtests lie. Even though Alpaca charges no
commission, model slippage explicitly so backtested edges survive contact with
reality. The same numbers drive the ``PaperSimBroker`` fill price.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..execution.paper_sim import PaperSimBroker


@dataclass
class CostModel:
    # Per-side slippage in basis points. Raised from 2 -> 5 bps because the
    # relaxed liquidity floor admits lower-liquidity names, which slip more.
    # Tighten this only if you measure real fills that justify it.
    slippage_bps: float = 5.0
    commission_per_share: float = 0.0    # Alpaca = 0; model anyway

    def build_broker(self, starting_cash: float) -> PaperSimBroker:
        return PaperSimBroker(
            starting_cash=starting_cash,
            slippage_bps=self.slippage_bps,
            commission_per_share=self.commission_per_share,
        )
