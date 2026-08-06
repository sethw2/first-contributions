"""Strategy interface and the Signal it emits.

Strategies never size or place orders — they only describe intent. The engine
routes every signal through the RiskManager for sizing and validation. This
seam is what lets the backtester and live engine share the exact same strategy.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

from ..risk.models import Bar, Position, Side


@dataclass
class Signal:
    """An intent to open a position. Sizing/stops are finalized by the RiskManager."""

    symbol: str
    side: Side
    strength: float          # 0..1 ranking score; higher = more preferred (SELECTION only, never sizing)
    reference_price: float   # price the signal is based on (last close)
    atr: float               # for volatility-based stop sizing
    kind: str = ""           # "momentum" | "reversion"
    avg_volume: float = 0.0  # avg daily volume in shares (for the ADV participation cap)
    reason: str = ""         # human-readable rationale for the audit log


class Strategy(abc.ABC):
    """Common surface for all signal models."""

    name: str = "base"

    @abc.abstractmethod
    def generate_signals(self, market: Dict[str, List[Bar]], now: datetime,
                         open_symbols: List[str]) -> List[Signal]:
        """Return ranked entry signals for symbols not already held."""

    def should_exit(self, position: Position, bars: List[Bar], now: datetime) -> Optional[str]:
        """Optional strategy-level exit (signal invalidation).

        Price stops, take-profits, and the time stop are enforced by the engine;
        this hook is for model-specific exits. Return a reason string or None.
        """
        return None
