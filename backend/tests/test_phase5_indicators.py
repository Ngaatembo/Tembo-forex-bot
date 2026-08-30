import pytest

from app.technical_engine.indicators import (
    calculate_atr, calculate_rolling_max, calculate_rolling_min, calculate_rsi, calculate_slope,
)


def test_rsi_warmup_boundary_is_exactly_14_none_values():
    """Empirically verified boundary — see docs/phase-5-notes.md."""
    closes = [1.10 + 0.001 * ((i % 7) - 3) for i in range(30)]
    rsi = calculate_rsi(closes, period=14)
    assert all(v is None for v in rsi[:14])
    assert rsi[14] is not None


def test_rsi_bounded_between_0_and_100():
    closes = [1.10 + 0.001 * ((i % 7) - 3) for i in range(30)]
    rsi = calculate_rsi(closes, period=14)
    for v in rsi:
        if v is not None:
            assert 0.0 <= v <= 100.0


def test_rsi_flat_series_is_neutral_fifty():
    closes = [1.1000] * 20
    rsi = calculate_rsi(closes, period=14)
    assert rsi[14] == pytest.approx(50.0)


def test_rsi_rejects_invalid_period():
    with pytest.raises(ValueError):
        calculate_rsi([1.0, 2.0], period=0)


def test_rsi_does_not_use_future_values():
    closes = [1.10 + 0.001 * ((i % 5) - 2) for i in range(20)]
    without_future = calculate_rsi(closes, period=14)
    with_future = calculate_rsi(closes + [5.0, 5.0, 5.0], period=14)
    assert without_future[14] == with_future[14]


def test_atr_warmup_boundary_is_exactly_13_none_values():
    """Empirically verified boundary — see docs/phase-5-notes.md."""
    closes = [1.10 + 0.001 * ((i % 7) - 3) for i in range(30)]
    highs = [c + 0.002 for c in closes]
    lows = [c - 0.002 for c in closes]
    atr = calculate_atr(highs, lows, closes, period=14)
    assert all(v is None for v in atr[:13])
    assert atr[13] is not None


def test_atr_is_never_negative():
    closes = [1.10 + 0.001 * ((i % 7) - 3) for i in range(30)]
    highs = [c + 0.002 for c in closes]
    lows = [c - 0.002 for c in closes]
    atr = calculate_atr(highs, lows, closes, period=14)
    for v in atr:
        if v is not None:
            assert v >= 0


def test_atr_rejects_mismatched_lengths():
    with pytest.raises(ValueError):
        calculate_atr([1.0, 2.0], [1.0], [1.0, 2.0], period=14)


def test_atr_does_not_use_future_values():
    closes = [1.10 + 0.001 * ((i % 5) - 2) for i in range(20)]
    highs = [c + 0.002 for c in closes]
    lows = [c - 0.002 for c in closes]
    without_future = calculate_atr(highs, lows, closes, period=14)
    with_future = calculate_atr(highs + [5.5], lows + [4.5], closes + [5.0], period=14)
    assert without_future[13] == with_future[13]


def test_rolling_max_min_basic():
    values = [1.0, 3.0, 2.0, 5.0, 4.0]
    assert calculate_rolling_max(values, window=3) == [None, None, 3.0, 5.0, 5.0]
    assert calculate_rolling_min(values, window=3) == [None, None, 1.0, 2.0, 2.0]


def test_rolling_max_rejects_invalid_window():
    with pytest.raises(ValueError):
        calculate_rolling_max([1.0, 2.0], window=0)


def test_slope_basic():
    values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 10.0]
    slope = calculate_slope(values, lookback=2)
    # slope[2] = (values[2]-values[0])/2 = (3-1)/2 = 1.0
    # slope[6] = (values[6]-values[4])/2 = (10-5)/2 = 2.5
    assert slope[2] == pytest.approx(1.0)
    assert slope[6] == pytest.approx(2.5)
    assert slope[0] is None and slope[1] is None


def test_slope_none_when_either_endpoint_is_none():
    values = [None, None, 3.0, 4.0, 5.0]
    slope = calculate_slope(values, lookback=2)
    assert slope[2] is None  # values[0] is None
    assert slope[3] is None  # values[1] is None
    assert slope[4] is not None  # values[2]=3.0, values[4-2]=values[2]=3.0... both real


def test_slope_rejects_invalid_lookback():
    with pytest.raises(ValueError):
        calculate_slope([1.0, 2.0], lookback=0)
