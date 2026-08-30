"""
calculate_feature_snapshots(candles) — Phase 5's research feature
layer entrypoint.

Same architectural boundary as Phase 2's service.py: takes candles in,
returns FeatureSnapshot records out. No broker access, no database
access, no LLM access, no BUY/SELL/WAIT decision anywhere in this
module. Regime classification (regime.py) is deterministic rule
evaluation on already-computed indicators — not a prediction.

Reuses the SAME chronological-order precondition check as Phase 2
(imported directly, not reimplemented) — duplicate/out-of-order
candles are rejected here exactly as they are in technical_engine/service.py.
"""

from app.data_engine.market_data import Candle
from app.technical_engine.indicators import (
    calculate_atr, calculate_rolling_max, calculate_rolling_min, calculate_rsi,
    calculate_sma, calculate_slope,
)
from app.technical_engine.models import FeatureSnapshot
from app.technical_engine.regime import RegimeInputs, classify_regime
from app.technical_engine.service import _require_chronological_order

SMA_SLOPE_LOOKBACK = 5           # slope measured over the trailing 5 candles
RECENT_HIGH_LOW_WINDOW = 20      # "recent" high/low lookback, in candles
RSI_PERIOD = 14
ATR_PERIOD = 14


def calculate_feature_snapshots(candles: list[Candle]) -> list[FeatureSnapshot]:
    if not candles:
        return []

    _require_chronological_order(candles)

    closes = [c.close for c in candles]
    highs = [c.high for c in candles]
    lows = [c.low for c in candles]

    sma_10 = calculate_sma(closes, period=10)
    sma_50 = calculate_sma(closes, period=50)
    sma_50_slope = calculate_slope(sma_50, lookback=SMA_SLOPE_LOOKBACK)
    rsi_14 = calculate_rsi(closes, period=RSI_PERIOD)
    atr_14 = calculate_atr(highs, lows, closes, period=ATR_PERIOD)
    recent_high = calculate_rolling_max(highs, window=RECENT_HIGH_LOW_WINDOW)
    recent_low = calculate_rolling_min(lows, window=RECENT_HIGH_LOW_WINDOW)

    snapshots = []
    for i, candle in enumerate(candles):
        close = candle.close

        sma_distance = (
            sma_10[i] - sma_50[i] if sma_10[i] is not None and sma_50[i] is not None else None
        )
        sma_distance_pct = sma_distance / close if sma_distance is not None else None
        atr_percent = atr_14[i] / close if atr_14[i] is not None else None

        rolling_range = (
            recent_high[i] - recent_low[i]
            if recent_high[i] is not None and recent_low[i] is not None else None
        )
        distance_from_high = recent_high[i] - close if recent_high[i] is not None else None
        distance_from_low = close - recent_low[i] if recent_low[i] is not None else None

        regime = classify_regime(
            RegimeInputs(
                close=close, sma_50=sma_50[i], sma_50_slope=sma_50_slope[i],
                sma_distance_pct=sma_distance_pct, atr_percent=atr_percent,
            )
        )

        snapshots.append(
            FeatureSnapshot(
                timestamp=candle.timestamp, close=close,
                sma_10=sma_10[i], sma_50=sma_50[i], sma_50_slope=sma_50_slope[i],
                sma_distance=sma_distance, sma_distance_pct=sma_distance_pct,
                rsi_14=rsi_14[i],
                atr_14=atr_14[i], atr_percent=atr_percent,
                recent_high=recent_high[i], recent_low=recent_low[i],
                rolling_range=rolling_range,
                distance_from_high=distance_from_high, distance_from_low=distance_from_low,
                regime=regime.value,
            )
        )

    return snapshots
