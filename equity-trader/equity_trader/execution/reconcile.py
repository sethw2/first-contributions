"""Startup reconciliation.

Before the engine does anything, it must reconcile its local view against the
broker's actual positions and orders. Local state is never assumed to be truth:
a crash, a manual trade, or a partial fill can all leave them out of sync.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from ..risk.models import Position
from .broker import Broker, BrokerPosition


@dataclass
class ReconcileReport:
    broker_positions: List[BrokerPosition] = field(default_factory=list)
    orphaned_local: List[str] = field(default_factory=list)   # in local book, not at broker
    untracked_broker: List[str] = field(default_factory=list)  # at broker, not in local book
    canceled_open_orders: int = 0

    @property
    def clean(self) -> bool:
        return not self.orphaned_local and not self.untracked_broker


def reconcile(broker: Broker, local_positions: Dict[str, Position],
              cancel_open_orders: bool = True) -> ReconcileReport:
    """Compare local position book to the broker; optionally cancel stray orders.

    Returns a report the caller should log and act on. Untracked broker
    positions are dangerous (they have no stop in our book) and should be
    surfaced loudly — the safe default is for the engine to adopt them under a
    protective time+price stop or flatten them, per operator policy.
    """
    report = ReconcileReport()
    report.broker_positions = broker.get_positions()
    broker_symbols = {p.symbol for p in report.broker_positions}
    local_symbols = set(local_positions.keys())

    report.orphaned_local = sorted(local_symbols - broker_symbols)
    report.untracked_broker = sorted(broker_symbols - local_symbols)

    if cancel_open_orders:
        open_orders = broker.get_open_orders()
        if open_orders:
            broker.cancel_all_orders()
            report.canceled_open_orders = len(open_orders)

    # Drop local positions the broker no longer has (already exited elsewhere).
    for sym in report.orphaned_local:
        local_positions.pop(sym, None)

    return report
