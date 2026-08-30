"""
Time-series momentum / trend-following signal generators (Phase 11).

momentum[t] = close[t]/close[t-N] - 1 is a direct trailing comparison
(like SMA) — no special current-candle-exclusion trick is needed here,
unlike breakout.py's rolling-extremum problem: close[t-N] is a fixed
past point, not something that could trivially include candle t itself.

All three fire edge-triggered (once on the transition into a new
directional state), same discipline as crossover.py/breakout.py —
never repeated every candle the state holds.
"""

import pandas as pd

from app.data_engine.market_data import Candle
from app.strategy_engine.models import Signal
from app.technical_engine.models import FeatureSnapshot


def calculate_momentum(closes: list[float], lookback: int) -> list[float | None]:
    if lookback <= 0:
        raise ValueError(f"lookback must be a positive integer, got {lookback}")
    if not closes:
        return []
    series = pd.Series(closes, dtype="float64")
    shifted = series.shift(lookback)
    momentum = series / shifted - 1
    return [None if pd.isna(v) else float(v) for v in momentum]


def _sign(x: float | None) -> int | None:
    if x is None:
        return None
    if x > 0:
        return 1
    if x < 0:
        return -1
    return 0


def _make_signal(candle: Candle, symbol: str, direction: str, reason: str) -> Signal:
    return Signal(timestamp=candle.timestamp, symbol=symbol, direction=direction, sma_10=None, sma_50=None, reason=reason)


def detect_momentum_signals(candles: list[Candle], lookback: int, symbol: str) -> list[Signal]:
    """T1 — pure sign-of-momentum."""
    if not candles:
        return []
    closes = [c.close for c in candles]
    momentum = calculate_momentum(closes, lookback)

    signals = []
    prev_sign = None
    for i, candle in enumerate(candles):
        s = _sign(momentum[i])
        if s is None:
            signals.append(_make_signal(candle, symbol, "WAIT", "Insufficient data — inside momentum warm-up period."))
            prev_sign = None
            continue
        if s == 1 and prev_sign != 1:
            signals.append(_make_signal(candle, symbol, "BUY", f"{lookback}-candle momentum turned positive."))
        elif s == -1 and prev_sign != -1:
            signals.append(_make_signal(candle, symbol, "SELL", f"{lookback}-candle momentum turned negative."))
        else:
            signals.append(_make_signal(candle, symbol, "WAIT", "No new momentum-direction change."))
        prev_sign = s
    return signals


def detect_vol_normalized_signals(
    candles: list[Candle], features: list[FeatureSnapshot], lookback: int, threshold: float, symbol: str
) -> list[Signal]:
    """T2 — momentum sign, only when |momentum|/atr_percent exceeds threshold."""
    if not candles:
        return []
    closes = [c.close for c in candles]
    momentum = calculate_momentum(closes, lookback)

    signals = []
    prev_state = None  # 1, -1, or None (no qualifying signal)
    for i, candle in enumerate(candles):
        m, atr_pct = momentum[i], features[i].atr_percent
        if m is None or atr_pct is None or atr_pct == 0:
            signals.append(_make_signal(candle, symbol, "WAIT", "Insufficient data (momentum or ATR% warm-up)."))
            prev_state = None
            continue

        qualifies = abs(m) / atr_pct > threshold
        s = _sign(m) if qualifies else 0

        if s == 1 and prev_state != 1:
            signals.append(_make_signal(candle, symbol, "BUY", f"Vol-normalized momentum positive and > {threshold}x ATR%."))
        elif s == -1 and prev_state != -1:
            signals.append(_make_signal(candle, symbol, "SELL", f"Vol-normalized momentum negative and > {threshold}x ATR%."))
        else:
            signals.append(_make_signal(candle, symbol, "WAIT", "No qualifying vol-normalized momentum change."))
        prev_state = s


    return signals


def detect_confirmed_trend_signals(
    candles: list[Candle], primary_lookback: int, secondary_lookback: int, symbol: str
) -> list[Signal]:
    """T3 — requires primary AND secondary lookback momentum to agree in sign."""
    if not candles:
        return []
    closes = [c.close for c in candles]
    primary = calculate_momentum(closes, primary_lookback)
    secondary = calculate_momentum(closes, secondary_lookback)

    signals = []
    prev_state = None
    for i, candle in enumerate(candles):
        p, sdy = primary[i], secondary[i]
        if p is None or sdy is None:
            signals.append(_make_signal(candle, symbol, "WAIT", "Insufficient data (primary or secondary momentum warm-up)."))
            prev_state = None
            continue

        p_sign, s_sign = _sign(p), _sign(sdy)
        agreed = p_sign if (p_sign == s_sign and p_sign != 0) else 0

        if agreed == 1 and prev_state != 1:
            signals.append(_make_signal(candle, symbol, "BUY", "Primary and secondary momentum both positive."))
        elif agreed == -1 and prev_state != -1:
            signals.append(_make_signal(candle, symbol, "SELL", "Primary and secondary momentum both negative."))
        else:
            signals.append(_make_signal(candle, symbol, "WAIT", "Primary/secondary momentum disagree or unchanged."))
        prev_state = agreed
    return signals
