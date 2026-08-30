"""
Output shape for the technical engine.

TechnicalFeature carries only what's been calculated so far (Phase 2:
close, sma_10, sma_50). Later phases (EMA, RSI, MACD, ATR, Bollinger
Bands, ADX, volatility, momentum, regime) extend this dataclass rather
than replacing it, so existing consumers never break when a new
feature is added.
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class TechnicalFeature:
    timestamp: datetime
    close: float
    sma_10: float | None
    sma_50: float | None
