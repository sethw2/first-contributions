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
    slippage_bps: float = 2.0            # per-side slippage in basis points
    commission_per_share: float = 0.0    # Alpaca = 0; model anyway

    def build_broker(self, starting_cash: float) -> PaperSimBroker:
        return PaperSimBroker(
            starting_cash=starting_cash,
            slippage_bps=self.slippage_bps,
            commission_per_share=self.commission_per_share,
        )
