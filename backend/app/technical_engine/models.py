"""
Output shapes for the technical engine.

TechnicalFeature carries Phase 2's original set (close, sma_10,
sma_50) and is left untouched — Phase 3/4 strategy/backtesting code
depends on exactly this shape. FeatureSnapshot (Phase 5) is a separate,
larger dataclass for research use; see its own docstring below for why
it isn't an in-place extension of TechnicalFeature.
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class TechnicalFeature:
    timestamp: datetime
    close: float
    sma_10: float | None
    sma_50: float | None


@dataclass
class FeatureSnapshot:
    """
    Phase 5's extended research feature set. A superset of what
    TechnicalFeature carries — kept as a SEPARATE dataclass rather than
    extending TechnicalFeature in place, so Phase 3/4's strategy and
    backtesting code (which only ever asked for sma_10/sma_50) is
    completely unaffected by this phase's additions.

    `regime` is an algorithmic classification (see regime.py) — a
    label, not a ground truth about market conditions.
    """
    timestamp: datetime
    close: float

    sma_10: float | None
    sma_50: float | None
    sma_50_slope: float | None
    sma_distance: float | None       # sma_10 - sma_50, in price units
    sma_distance_pct: float | None   # sma_distance / close

    rsi_14: float | None

    atr_14: float | None
    atr_percent: float | None        # atr_14 / close

    recent_high: float | None
    recent_low: float | None
    rolling_range: float | None      # recent_high - recent_low
    distance_from_high: float | None  # recent_high - close
    distance_from_low: float | None   # close - recent_low

    regime: str  # MarketRegime value — see regime.py
