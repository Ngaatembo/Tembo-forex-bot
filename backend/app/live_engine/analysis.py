"""Deterministic live-market analysis built on verified candle data.

This layer does not predict price and does not emit BUY/SELL decisions.
It summarizes observable technical conditions from completed candles:
trend, momentum, volatility, support/resistance, and confirmed swing
structure. The caller must provide normalized/validated candles.
"""

from dataclasses import asdict
from typing import Any

from app.data_engine.market_data import Candle
from app.technical_engine.features import calculate_feature_snapshots


def _last_snapshot(candles: list[Candle]) -> Any:
    snapshots = calculate_feature_snapshots(candles)
    if not snapshots:
        return None
    return snapshots[-1]


def _round(value: float | None, digits: int = 8) -> float | None:
    return round(value, digits) if value is not None else None


def _confirmed_swings(candles: list[Candle], strength: int = 2) -> tuple[list[float], list[float]]:
    """Return only pivots confirmed by candles on both sides."""
    highs: list[float] = []
    lows: list[float] = []
    last_confirmable = len(candles) - strength
    for i in range(strength, max(strength, last_confirmable)):
        left = candles[i - strength:i]
        right = candles[i + 1:i + strength + 1]
        if len(right) < strength:
            continue
        high = candles[i].high
        low = candles[i].low
        if high > max(c.high for c in left + right):
            highs.append(high)
        if low < min(c.low for c in left + right):
            lows.append(low)
    return highs, lows


def _structure(candles: list[Candle]) -> dict[str, Any]:
    swing_highs, swing_lows = _confirmed_swings(candles)
    if len(swing_highs) >= 2 and len(swing_lows) >= 2:
        higher_high = swing_highs[-1] > swing_highs[-2]
        higher_low = swing_lows[-1] > swing_lows[-2]
        lower_high = swing_highs[-1] < swing_highs[-2]
        lower_low = swing_lows[-1] < swing_lows[-2]
        if higher_high and higher_low:
            label = "HIGHER_HIGH_HIGHER_LOW"
        elif lower_high and lower_low:
            label = "LOWER_HIGH_LOWER_LOW"
        else:
            label = "MIXED_STRUCTURE"
    else:
        label = "INSUFFICIENT_SWINGS"

    return {
        "label": label,
        "confirmed_swing_high": _round(swing_highs[-1] if swing_highs else None),
        "previous_swing_high": _round(swing_highs[-2] if len(swing_highs) >= 2 else None),
        "confirmed_swing_low": _round(swing_lows[-1] if swing_lows else None),
        "previous_swing_low": _round(swing_lows[-2] if len(swing_lows) >= 2 else None),
    }


def analyze_candles(candles: list[Candle]) -> dict[str, Any]:
    if len(candles) < 50:
        return {
            "status": "insufficient_data",
            "reason": "At least 50 completed candles are required for the SMA50-based analysis.",
            "trend": None,
            "momentum": None,
            "volatility": None,
            "support_resistance": None,
            "market_structure": _structure(candles) if candles else None,
        }

    snapshot = _last_snapshot(candles)
    if snapshot is None:
        return {"status": "insufficient_data", "reason": "Technical features are not warmed up."}

    trend_label = {
        "TRENDING_UP": "UP",
        "TRENDING_DOWN": "DOWN",
        "RANGING": "RANGE",
        "HIGH_VOLATILITY": "UNSTABLE",
        "LOW_VOLATILITY": "QUIET",
        "UNKNOWN": "UNKNOWN",
    }.get(snapshot.regime, "UNKNOWN")

    if snapshot.rsi_14 is None:
        momentum_state = "UNKNOWN"
    elif snapshot.rsi_14 >= 70:
        momentum_state = "OVERBOUGHT"
    elif snapshot.rsi_14 <= 30:
        momentum_state = "OVERSOLD"
    elif snapshot.rsi_14 >= 55:
        momentum_state = "POSITIVE"
    elif snapshot.rsi_14 <= 45:
        momentum_state = "NEGATIVE"
    else:
        momentum_state = "NEUTRAL"

    swing_highs, swing_lows = _confirmed_swings(candles)
    resistance = snapshot.recent_high
    support = snapshot.recent_low
    if swing_highs:
        resistance = max(resistance or swing_highs[-1], swing_highs[-1])
    if swing_lows:
        support = min(support or swing_lows[-1], swing_lows[-1])

    return {
        "status": "available",
        "as_of": snapshot.timestamp.isoformat(),
        "close": _round(snapshot.close),
        "trend": {
            "state": trend_label,
            "regime": snapshot.regime,
            "sma_10": _round(snapshot.sma_10),
            "sma_50": _round(snapshot.sma_50),
            "sma_50_slope": _round(snapshot.sma_50_slope),
            "sma_distance_pct": _round(snapshot.sma_distance_pct, 6),
        },
        "momentum": {
            "state": momentum_state,
            "rsi_14": _round(snapshot.rsi_14, 2),
        },
        "volatility": {
            "state": snapshot.regime if snapshot.regime in {"HIGH_VOLATILITY", "LOW_VOLATILITY"} else "NORMAL",
            "atr_14": _round(snapshot.atr_14),
            "atr_percent": _round(snapshot.atr_percent, 6),
        },
        "support_resistance": {
            "support": _round(support),
            "resistance": _round(resistance),
            "recent_high": _round(snapshot.recent_high),
            "recent_low": _round(snapshot.recent_low),
            "rolling_range": _round(snapshot.rolling_range),
        },
        "market_structure": _structure(candles),
        "feature_snapshot": {
            key: value for key, value in asdict(snapshot).items()
        },
    }
