"""
Instrument/Timeframe Adapter.

WHAT THIS CAN ACTUALLY COMPUTE from historical CSV data alone: mean
price, price precision (inferred from the data), and — the specific
gap Phase 13.1 found and hand-patched — a NOTIONALLY-COMPARABLE
position size derived from mean price ratios. This generalizes that
one-off fix into tested, reusable infrastructure.

WHAT THIS CANNOT COMPUTE, and says so explicitly rather than
guessing: real broker contract specs — tick size, tick value, point
value, minimum position increment, margin requirements. Historical
OHLC data has no such information; a real broker/data-vendor API
would be needed. Every field for this is `None`, not a fabricated
number.
"""

from dataclasses import dataclass
from typing import Optional

from app.data_engine.market_data import Candle

TIMEFRAME_TO_HOURS = {"m5": 5 / 60, "m15": 15 / 60, "h1": 1.0, "h4": 4.0, "d1": 24.0}


@dataclass(frozen=True)
class InstrumentTimeframeInfo:
    instrument: str
    timeframe: str
    mean_price: float
    price_precision_decimals: int
    candle_duration_hours: Optional[float] = None

    tick_size: Optional[float] = None
    tick_value: Optional[float] = None
    point_value: Optional[float] = None
    minimum_position_size: Optional[float] = None
    position_increment: Optional[float] = None


def build_instrument_timeframe_info(instrument: str, timeframe: str, candles: list) -> InstrumentTimeframeInfo:
    if not candles:
        raise ValueError("Cannot build instrument info from an empty candle list.")

    closes = [c.close for c in candles]
    mean_price = sum(closes) / len(closes)

    max_decimals = 0
    for c in closes[:200]:
        s = f"{c:.10f}".rstrip("0")
        decimals = len(s.split(".")[1]) if "." in s else 0
        max_decimals = max(max_decimals, decimals)

    return InstrumentTimeframeInfo(
        instrument=instrument, timeframe=timeframe, mean_price=mean_price,
        price_precision_decimals=min(max_decimals, 5),
        candle_duration_hours=TIMEFRAME_TO_HOURS.get(timeframe.lower()),
    )


def compute_notionally_comparable_position_size(
    reference_info: InstrumentTimeframeInfo, target_info: InstrumentTimeframeInfo, reference_position_size: float
) -> float:
    """
    Generalizes Phase 13.1's exact hand-derivation: a fixed unit-count
    position size does NOT represent comparable dollar notional
    exposure across instruments with different price scales. This
    scales `reference_position_size` (established for
    `reference_info`'s instrument, e.g. EUR/USD's 10,000) by the ratio
    of mean prices, so notional exposure (position_size x mean_price)
    stays comparable across instruments.
    """
    if target_info.mean_price <= 0:
        raise ValueError("target instrument's mean price must be positive.")
    return reference_position_size * (reference_info.mean_price / target_info.mean_price)
