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
