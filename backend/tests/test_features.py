import pytest

from app.technical_engine.features import calculate_feature_snapshots
from app.technical_engine.regime import MarketRegime
from tests.fixtures.regime_fixtures import (
    high_volatility_market, insufficient_data_market, sideways_ranging_market,
    steadily_falling_market, steadily_rising_market,
)
from tests.fixtures.technical_eurusd_candles import synthetic_eurusd_50_candles


def test_empty_candles_returns_empty_snapshots():
    assert calculate_feature_snapshots([]) == []


def test_chronological_order_is_enforced():
    """Test 9/10 — reuses technical_engine.service's own precondition check."""
    candles = synthetic_eurusd_50_candles()
    shuffled = [candles[1], candles[0]] + candles[2:]
    with pytest.raises(ValueError, match="chronological"):
        calculate_feature_snapshots(shuffled)


def test_duplicate_timestamps_rejected():
    candles = synthetic_eurusd_50_candles()
    with_dup = candles[:2] + [candles[1]] + candles[2:]
    with pytest.raises(ValueError, match="chronological"):
        calculate_feature_snapshots(with_dup)


def test_deterministic_across_runs():
    candles = steadily_rising_market()
    first = calculate_feature_snapshots(candles)
    second = calculate_feature_snapshots(candles)
    assert [s.regime for s in first] == [s.regime for s in second]
    assert [s.rsi_14 for s in first] == [s.rsi_14 for s in second]


def test_future_candles_do_not_change_past_snapshots():
    """Lookahead-bias test for the whole Phase 5 feature pipeline."""
    candles = steadily_rising_market(n=80)
    baseline = calculate_feature_snapshots(candles)

    from datetime import timedelta
    from app.data_engine.market_data import Candle
    future = [
        Candle(
            symbol="EUR/USD", timeframe="1h",
            timestamp=candles[-1].timestamp + timedelta(hours=i + 1),
            open=5.0, high=5.5, low=4.5, close=5.0 + i, volume=999999,
        )
        for i in range(10)
    ]
    extended = calculate_feature_snapshots(candles + future)

    for i in range(len(candles)):
        assert baseline[i].regime == extended[i].regime
        assert baseline[i].rsi_14 == extended[i].rsi_14
        assert baseline[i].atr_14 == extended[i].atr_14
        assert baseline[i].sma_50_slope == extended[i].sma_50_slope


def test_regime_unknown_during_warmup():
    """Test 8 — insufficient data must yield UNKNOWN, never a fabricated regime."""
    candles = insufficient_data_market()
    snapshots = calculate_feature_snapshots(candles)
    assert all(s.regime == MarketRegime.UNKNOWN.value for s in snapshots)
    assert all(s.sma_50 is None for s in snapshots)


def test_steadily_rising_fixture_classifies_as_trending_up():
    candles = steadily_rising_market()
    snapshots = calculate_feature_snapshots(candles)
    assert snapshots[-1].regime == MarketRegime.TRENDING_UP.value


def test_steadily_falling_fixture_classifies_as_trending_down():
    candles = steadily_falling_market()
    snapshots = calculate_feature_snapshots(candles)
    assert snapshots[-1].regime == MarketRegime.TRENDING_DOWN.value


def test_ranging_fixture_classifies_as_ranging():
    candles = sideways_ranging_market()
    snapshots = calculate_feature_snapshots(candles)
    assert snapshots[-1].regime == MarketRegime.RANGING.value


def test_high_volatility_fixture_classifies_as_high_volatility():
    candles = high_volatility_market()
    snapshots = calculate_feature_snapshots(candles)
    assert snapshots[-1].regime == MarketRegime.HIGH_VOLATILITY.value


def test_sma_distance_matches_phase2_sma_values():
    """Cross-check against the same SMA math Phase 2 already validated."""
    candles = synthetic_eurusd_50_candles()
    snapshots = calculate_feature_snapshots(candles)
    last = snapshots[-1]
    assert last.sma_distance == pytest.approx(last.sma_10 - last.sma_50)
    assert last.sma_distance_pct == pytest.approx(last.sma_distance / last.close)


def test_recent_high_low_and_rolling_range_consistent():
    candles = steadily_rising_market(n=30)
    snapshots = calculate_feature_snapshots(candles)
    last = snapshots[-1]
    if last.recent_high is not None:
        assert last.rolling_range == pytest.approx(last.recent_high - last.recent_low)
        assert last.distance_from_high == pytest.approx(last.recent_high - last.close)
        assert last.distance_from_low == pytest.approx(last.close - last.recent_low)
