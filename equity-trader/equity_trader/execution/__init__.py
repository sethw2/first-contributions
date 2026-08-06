"""Execution layer: broker abstraction, simulated + Alpaca adapters, reconciliation."""

from .broker import Broker, BrokerPosition
from .paper_sim import PaperSimBroker
from .reconcile import ReconcileReport, reconcile

__all__ = ["Broker", "BrokerPosition", "PaperSimBroker", "ReconcileReport", "reconcile"]

# AlpacaBroker is intentionally NOT imported here so the package loads without
# alpaca-py installed. Import it explicitly where needed:
#     from equity_trader.execution.alpaca_broker import AlpacaBroker
