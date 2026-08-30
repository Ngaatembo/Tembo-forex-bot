import pytest

from app.data_engine.market_data import Candle
from app.technical_engine.service import calculate_features
from tests.fixtures.eurusd_candles import clean_eurusd_candles
from tests.fixtures.technical_eurusd_candles import synthetic_eurusd_50_candles


def test_sma10_first_valid_value_at_candle_10():
    """Test 2 — SMA10 warm-up boundary."""
    candles = synthetic_eurusd_50_candles()
    features = calculate_features(candles)

    assert all(f.sma_10 is None for f in features[:9])
    assert features[9].sma_10 is not None


def test_sma50_first_valid_value_at_candle_50():
    """Test 3 — SMA50 warm-up boundary (fixture has exactly 50 candles)."""
    candles = synthetic_eurusd_50_candles()
    assert len(candles) == 50
    features = calculate_features(candles)

    assert all(f.sma_50 is None for f in features[:49])
    assert features[49].sma_50 is not None


def test_warmup_period_counts_exactly():
    """Test 4 — exactly 9 unavailable SMA10 values, exactly 49 unavailable SMA50 values."""
    candles = synthetic_eurusd_50_candles()
    features = calculate_features(candles)

    sma10_none_count = sum(1 for f in features if f.sma_10 is None)
    sma50_none_count = sum(1 for f in features if f.sma_50 is None)

    assert sma10_none_count == 9
    assert sma50_none_count == 49


def test_chronological_alignment():
    """Test 6 — each feature's timestamp matches its source candle exactly."""
    candles = synthetic_eurusd_50_candles()
    features = calculate_features(candles)

    for candle, feature in zip(candles, features):
        assert feature.timestamp == candle.timestamp
        assert feature.close == candle.close


def test_out_of_order_candles_raise_clearly():
    """Section 6 — must fail loudly on unsorted input, never silently compute wrong results."""
    candles = synthetic_eurusd_50_candles()
    shuffled = [candles[1], candles[0]] + candles[2:]  # swap first two

    with pytest.raises(ValueError, match="chronological"):
        calculate_features(shuffled)


def test_duplicate_timestamps_raise_clearly():
    candles = clean_eurusd_candles()
    with_dup = candles[:2] + [candles[1]] + candles[2:]

    with pytest.raises(ValueError, match="chronological"):
        calculate_features(with_dup)


def test_empty_candle_list_returns_empty_features():
    assert calculate_features([]) == []


def test_deterministic_across_runs():
    """Test 8, at the service level."""
    candles = synthetic_eurusd_50_candles()
    first = calculate_features(candles)
    second = calculate_features(candles)

    assert [f.sma_10 for f in first] == [f.sma_10 for f in second]
    assert [f.sma_50 for f in first] == [f.sma_50 for f in second]


def test_realistic_eurusd_fixture_produces_sane_sma_values():
    """
    Test 10 — the fixture is clearly-labeled synthetic data (see
    tests/fixtures/technical_eurusd_candles.py docstring), used only to
    confirm SMA values land in a sane range relative to the price series
    they were computed from — not to validate against any real market data.
    """
    candles = synthetic_eurusd_50_candles()
    features = calculate_features(candles)

    closes = [c.close for c in candles]
    last_sma10 = features[-1].sma_10
    last_sma50 = features[-1].sma_50

    assert min(closes) <= last_sma10 <= max(closes)
    assert min(closes) <= last_sma50 <= max(closes)
