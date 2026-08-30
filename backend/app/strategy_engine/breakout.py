"""
Market-structure breakout strategy.

WHY THIS ISN'T EXPRESSED VIA app.research.hypothesis.Condition:
Phase 7 documented that Condition can only compare fields within a
SINGLE candle's own FeatureSnapshot — it has no way to express "this
candle vs. a LAGGED prior value" (the exact gap that made Phase 7's
own breakout hypothesis untestable, since recent_high/recent_low
include the current candle by construction). A real breakout signal
NEEDS a lagged range, so this strategy is bespoke code — the same
architectural choice Phase 3 made for the SMA crossover, which also
isn't expressed via the generic Condition system.

LOOKAHEAD PROTECTION — the core guarantee of this module:
`prior_high[t]` / `prior_low[t]` are computed from candles
[t-lookback, t-1] ONLY — candle t's own high/low never enter its own
threshold. This is achieved by shifting the high/low series by 1
BEFORE taking the rolling max/min (see calculate_prior_range) — the
same shift-then-roll technique already used correctly in
technical_engine/indicators.py for ATR's previous-close reference.

FIRING SEMANTICS: same as every other signal generator in this
project — fires only on the transition into a breakout state, never
repeated on every candle price remains beyond the (lagged) range.
"""

import pandas as pd

from app.data_engine.market_data import Candle
from app.strategy_engine.models import Signal


def calculate_prior_range(
    highs: list[float], lows: list[float], lookback: int
) -> tuple[list[float | None], list[float | None]]:
    """
    prior_high[t] = max(highs[t-lookback : t])   — the `lookback` candles
    STRICTLY BEFORE t, excluding t's own high.
    prior_low[t] is the mirror, using lows.

    None for the first `lookback` candles (no full prior window exists yet).
    """
    if lookback <= 0:
        raise ValueError(f"lookback must be a positive integer, got {lookback}")
    if not highs:
        return [], []
    if len(highs) != len(lows):
        raise ValueError("highs and lows must be the same length.")

    high_series = pd.Series(highs, dtype="float64")
    low_series = pd.Series(lows, dtype="float64")

    # shift(1) BEFORE rolling is what excludes the current candle — the
    # window for row t after the shift covers original rows [t-lookback, t-1].
    prior_high = high_series.shift(1).rolling(window=lookback, min_periods=lookback).max()
    prior_low = low_series.shift(1).rolling(window=lookback, min_periods=lookback).min()

    return (
        [None if pd.isna(v) else float(v) for v in prior_high],
        [None if pd.isna(v) else float(v) for v in prior_low],
    )


def detect_breakout_signals(
    candles: list[Candle], lookback: int, symbol: str
) -> list[Signal]:
    if not candles:
        return []

    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    prior_high, prior_low = calculate_prior_range(highs, lows, lookback)

    signals: list[Signal] = []
    prev_above: bool | None = None
    prev_below: bool | None = None

    for i, candle in enumerate(candles):
        ph, pl = prior_high[i], prior_low[i]

        if ph is None or pl is None:
            signals.append(
                Signal(
                    timestamp=candle.timestamp, symbol=symbol, direction="WAIT",
                    sma_10=None, sma_50=None,
                    reason="Insufficient data — inside prior-range warm-up period.",
                )
            )
            prev_above, prev_below = None, None
            continue

        above_now = candle.close > ph
        below_now = candle.close < pl

        if above_now and not prev_above:
            direction, reason = "BUY", f"Close broke above the prior {lookback}-candle high."
        elif below_now and not prev_below:
            direction, reason = "SELL", f"Close broke below the prior {lookback}-candle low."
        else:
            direction, reason = "WAIT", "No new breakout on this candle."

        signals.append(
            Signal(
                timestamp=candle.timestamp, symbol=symbol, direction=direction,
                sma_10=None, sma_50=None, reason=reason,
            )
        )
        prev_above, prev_below = above_now, below_now

    return signals
