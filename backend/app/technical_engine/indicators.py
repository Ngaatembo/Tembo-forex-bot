"""
Deterministic mathematical indicators.

This module knows nothing about candles, timestamps, brokers, or
databases — it operates purely on ordered numeric sequences. That
separation is deliberate: it's what lets calculate_sma() be tested
with a trivial [1, 2, 3, 4, 5] list, independent of anything forex-
specific, and it's what keeps this module free of database access
per the technical-engine architectural boundary (see docs/phase-2-notes.md).
"""

import pandas as pd


def calculate_sma(values: list[float], period: int) -> list[float | None]:
    """
    Trailing simple moving average.

    SMA[t] = mean(values[t-period+1 : t+1])  — i.e. the current value
    and the (period-1) values before it. This is a TRAILING window,
    not a centered one: SMA[t] never depends on any value at an index
    greater than t. That property is what makes it safe to use in a
    backtest — see test_indicators.py::test_sma_does_not_use_future_values,
    which specifically proves this.

    Returns a list the same length as `values`. Positions before the
    warm-up period (the first `period - 1` entries) are None — never
    fabricated, per the project's rule against inventing values for
    periods where insufficient data exists.

    Raises ValueError for period <= 0. A period larger than len(values)
    is valid input (it just means every position is None) — that is
    normal near the start of a data set, not an error.
    """
    if period <= 0:
        raise ValueError(f"period must be a positive integer, got {period}")

    if not values:
        return []

    series = pd.Series(values, dtype="float64")
    # min_periods=period (equal to the window size) is what makes this
    # trailing-only and warm-up-respecting: pandas' default rolling
    # window is already trailing (never centered) unless you pass
    # center=True, which we deliberately never do here.
    rolling_mean = series.rolling(window=period, min_periods=period).mean()

    return [None if pd.isna(v) else float(v) for v in rolling_mean]


def calculate_rsi(closes: list[float], period: int = 14) -> list[float | None]:
    """
    Wilder-style RSI (the standard definition used by most platforms).

    Uses Wilder smoothing (an exponential moving average with
    alpha=1/period) on the up-moves and down-moves separately, which
    is what distinguishes real RSI from a naive "average gain over
    average loss on a plain rolling window" implementation.

    Returns None for the warm-up period. A flat price series (zero
    average gain AND zero average loss over the whole window) returns
    50.0 (neutral) rather than NaN — this is a documented special
    case, not left to divide-by-zero.
    """
    if period <= 0:
        raise ValueError(f"period must be a positive integer, got {period}")
    if not closes:
        return []

    series = pd.Series(closes, dtype="float64")
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    # avg_gain == avg_loss == 0 (a perfectly flat window) produces 0/0 = NaN
    # in the rs calculation above — treat that specific case as neutral (50),
    # not as "insufficient data" (which is already handled by min_periods).
    flat_window = (avg_gain == 0) & (avg_loss == 0)
    rsi = rsi.where(~flat_window, 50.0)

    return [None if pd.isna(v) else float(v) for v in rsi]


def calculate_atr(
    highs: list[float], lows: list[float], closes: list[float], period: int = 14
) -> list[float | None]:
    """
    Wilder-style Average True Range.

    True Range at t = max(high[t]-low[t], |high[t]-close[t-1]|, |low[t]-close[t-1]|).
    The first candle has no previous close, so its True Range falls
    back to simply high[0]-low[0] — standard convention — and ATR
    itself still returns None until `period` True Range values exist.
    """
    if period <= 0:
        raise ValueError(f"period must be a positive integer, got {period}")
    if not highs:
        return []
    if not (len(highs) == len(lows) == len(closes)):
        raise ValueError("highs, lows, and closes must be the same length.")

    high = pd.Series(highs, dtype="float64")
    low = pd.Series(lows, dtype="float64")
    close = pd.Series(closes, dtype="float64")
    prev_close = close.shift(1)

    tr_components = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    )
    true_range = tr_components.max(axis=1, skipna=True)
    # skipna above means row 0 (no prev_close) falls back to high-low only.

    atr = true_range.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    return [None if pd.isna(v) else float(v) for v in atr]


def calculate_rolling_max(values: list[float], window: int) -> list[float | None]:
    if window <= 0:
        raise ValueError(f"window must be a positive integer, got {window}")
    if not values:
        return []
    series = pd.Series(values, dtype="float64")
    result = series.rolling(window=window, min_periods=window).max()
    return [None if pd.isna(v) else float(v) for v in result]


def calculate_rolling_min(values: list[float], window: int) -> list[float | None]:
    if window <= 0:
        raise ValueError(f"window must be a positive integer, got {window}")
    if not values:
        return []
    series = pd.Series(values, dtype="float64")
    result = series.rolling(window=window, min_periods=window).min()
    return [None if pd.isna(v) else float(v) for v in result]


def calculate_slope(values: list, lookback: int) -> list:
    """
    slope[t] = (values[t] - values[t-lookback]) / lookback

    A simple trailing rate-of-change, used here for SMA50's slope.
    Requires values[t] AND values[t-lookback] to both be non-None —
    if either is still in ITS OWN warm-up period, the slope is None
    too (never fabricated from a partial comparison).
    """
    if lookback <= 0:
        raise ValueError(f"lookback must be a positive integer, got {lookback}")

    result = []
    for i in range(len(values)):
        if i < lookback or values[i] is None or values[i - lookback] is None:
            result.append(None)
        else:
            result.append((values[i] - values[i - lookback]) / lookback)
    return result
