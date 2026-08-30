"""
Signal output shape for the strategy engine.

Direction is one of "BUY", "SELL", "WAIT" — never anything else.
`reason` exists so every signal is explainable from stored data
without needing to re-derive it, per the project's rule that every
major decision must be explainable.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

Direction = Literal["BUY", "SELL", "WAIT"]


@dataclass
class Signal:
    timestamp: datetime
    symbol: str
    direction: Direction
    sma_10: float | None
    sma_50: float | None
    reason: str
