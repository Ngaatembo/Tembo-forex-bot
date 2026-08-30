import pytest

from app.technical_engine.indicators import calculate_sma


def test_sma_matches_manual_calculation():
    """Test 1 — a tiny sequence where the expected SMA can be hand-checked."""
    values = [1, 2, 3, 4, 5]
    result = calculate_sma(values, period=3)
    expected = [None, None, 2.0, 3.0, 4.0]
    assert result == expected


def test_sma_rejects_zero_period():
    """Test 7 (part 1) — invalid period."""
    with pytest.raises(ValueError):
        calculate_sma([1, 2, 3], period=0)


def test_sma_rejects_negative_period():
    """Test 7 (part 2) — invalid period."""
    with pytest.raises(ValueError):
        calculate_sma([1, 2, 3], period=-5)


def test_sma_is_deterministic():
    """Test 8 — same input, run twice, identical output."""
    values = [1.1, 1.2, 1.15, 1.3, 1.25, 1.4, 1.35]
    first_run = calculate_sma(values, period=3)
    second_run = calculate_sma(values, period=3)
    assert first_run == second_run


def test_sma_with_insufficient_data_returns_all_none():
    """Test 9 — fewer values than the period; must not crash."""
    result = calculate_sma([1.0, 2.0, 3.0], period=50)
    assert result == [None, None, None]


def test_sma_empty_input():
    assert calculate_sma([], period=10) == []


def test_sma_does_not_use_future_values():
    """
    Test 5 — the specific lookahead-bias check. If we compute SMA3 over
    [1, 2, 3], then compute it again over [1, 2, 3, 100] (a huge future
    value appended), the SMA value AT index 2 must be identical in both
    runs. If it changed, the calculation illegitimately used a future
    value that didn't exist yet at that point in time.
    """
    without_future = calculate_sma([1, 2, 3], period=3)
    with_future = calculate_sma([1, 2, 3, 100], period=3)
    assert without_future[2] == with_future[2] == 2.0
