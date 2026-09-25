"""
Instrument-aware position sizing.

TWO MODELS, and why both exist:
  "notional_price_unit" — size = risk_amount / stop_distance, in raw
    price units. This is the SAME model used throughout every phase
    of this project's backtesting (Phase 4 onward) and requires no
    broker-specific metadata — just entry/stop prices. This is the
    PRIMARY model here, because it's the only one this project's data
    can actually support: Phase 14's Instrument/Timeframe Adapter
    honestly reports tick_size/tick_value/point_value as None (no
    historical CSV data source provides real broker contract specs).
  "tick_based" — the broker-precise model (size derived from tick
    value, respecting minimum size and increment). NOT currently
    usable — every instrument this project has ever loaded has
    tick_size/tick_value = None. Implemented and tested here for when
    real broker metadata becomes available (a future live-broker connection),
    but calling it without that metadata FAILS CLOSED (raises), never
    silently substitutes a guess.

FAIL-SAFE RULE: if the required inputs for the requested model are
missing, this raises — position sizing NEVER returns a fabricated
size. The caller (risk_engine.py) is responsible for turning that
into an INSUFFICIENT_ACCOUNT_DATA / INVALID_INSTRUMENT decision.
"""

from math import isfinite

from app.research.instrument_adapter import InstrumentTimeframeInfo
from app.risk_engine.risk_models import PositionSizingDetail


def compute_position_size(
    *, equity: float, risk_pct: float, entry_price: float, stop_price: float,
    instrument_info: InstrumentTimeframeInfo | None = None,
) -> PositionSizingDetail:
    if not isfinite(equity) or equity <= 0:
        raise ValueError("equity must be finite and positive.")
    if not isfinite(risk_pct) or not (0 < risk_pct <= 1):
        raise ValueError("risk_pct must be finite and in (0, 1].")
    if not isfinite(entry_price) or not isfinite(stop_price) or entry_price <= 0 or stop_price <= 0:
        raise ValueError("entry_price and stop_price must be finite and positive.")

    stop_distance = abs(entry_price - stop_price)
    if not isfinite(stop_distance) or stop_distance <= 0:
        raise ValueError("stop_distance must be finite and positive — entry and stop cannot be equal.")

    risk_amount = equity * risk_pct

    if instrument_info is not None and instrument_info.tick_size is not None and instrument_info.tick_value is not None:
        ticks_at_risk = stop_distance / instrument_info.tick_size
        raw_size = risk_amount / (ticks_at_risk * instrument_info.tick_value)
        sizing_model = "tick_based"
        notes = f"Sized using tick_size={instrument_info.tick_size}, tick_value={instrument_info.tick_value}."
    else:
        raw_size = risk_amount / stop_distance
        sizing_model = "notional_price_unit"
        notes = (
            "Broker tick/point metadata unavailable — sized directly in price units "
            "(same model used throughout this project's backtesting). Real broker "
            "contract specs would be required for tick-precise live sizing."
        )

    final_size = raw_size
    if instrument_info is not None:
        if instrument_info.tick_size is not None and instrument_info.tick_size <= 0:
            raise ValueError("tick_size must be positive when supplied.")
        if instrument_info.tick_value is not None and (not isfinite(instrument_info.tick_value) or instrument_info.tick_value <= 0):
            raise ValueError("tick_value must be finite and positive when supplied.")
        if instrument_info.minimum_position_size is not None and (not isfinite(instrument_info.minimum_position_size) or instrument_info.minimum_position_size < 0):
            raise ValueError("minimum_position_size must be finite and non-negative when supplied.")
        if instrument_info.position_increment is not None and (not isfinite(instrument_info.position_increment) or instrument_info.position_increment < 0):
            raise ValueError("position_increment must be finite and non-negative when supplied.")
        if instrument_info.minimum_position_size is not None:
            if final_size < instrument_info.minimum_position_size:
                final_size = 0.0
                notes += " Calculated size below instrument minimum — sized to 0 (no trade)."
        if instrument_info.position_increment is not None and instrument_info.position_increment > 0 and final_size > 0:
            increments = int(final_size / instrument_info.position_increment)
            final_size = increments * instrument_info.position_increment

    return PositionSizingDetail(
        sizing_model=sizing_model, risk_amount=risk_amount, stop_distance=stop_distance,
        raw_position_size=raw_size, final_position_size=final_size, notes=notes,
    )
