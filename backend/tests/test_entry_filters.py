import pytest
from datetime import datetime, timedelta, timezone

from app.strategy_engine.entry_filters import filter_avoid_extreme_rsi, filter_avoid_low_volatility
from app.strategy_engine.models import Signal
from app.technical_engine.models import FeatureSnapshot

BASE = datetime(2024, 1, 8, 0, 0, tzinfo=timezone.utc)


def sig(hour: int, direction: str) -> Signal:
    return Signal(
        timestamp=BASE + timedelta(hours=hour), symbol="EUR/USD", direction=direction,
        sma_10=1.10, sma_50=1.09, reason="test",
    )


def feat(hour: int, regime: str = "RANGING", rsi: float = 50.0) -> FeatureSnapshot:
    return FeatureSnapshot(
        timestamp=BASE + timedelta(hours=hour), close=1.10,
        sma_10=1.10, sma_50=1.09, sma_50_slope=0.0, sma_distance=0.01, sma_distance_pct=0.009,
        rsi_14=rsi, atr_14=0.001, atr_percent=0.001,
        recent_high=1.11, recent_low=1.08, rolling_range=0.03,
        distance_from_high=0.01, distance_from_low=0.02, regime=regime,
    )


def test_low_volatility_filter_suppresses_only_matching_signals():
    signals = [sig(0, "BUY"), sig(1, "WAIT"), sig(2, "SELL")]
    features = [feat(0, regime="LOW_VOLATILITY"), feat(1, regime="RANGING"), feat(2, regime="TRENDING_DOWN")]

    result = filter_avoid_low_volatility(signals, features)

    assert result[0].direction == "WAIT"  # suppressed
    assert "suppressed" in result[0].reason
    assert result[1].direction == "WAIT"  # was already WAIT, untouched in meaning
    assert result[2].direction == "SELL"  # not low-vol, unaffected


def test_low_volatility_filter_never_upgrades_a_wait_to_a_signal():
    signals = [sig(0, "WAIT")]
    features = [feat(0, regime="TRENDING_UP")]
    result = filter_avoid_low_volatility(signals, features)
    assert result[0].direction == "WAIT"


def test_low_volatility_filter_rejects_mismatched_lengths():
    with pytest.raises(ValueError):
        filter_avoid_low_volatility([sig(0, "BUY")], [])


def test_extreme_rsi_filter_suppresses_overbought_buy():
    signals = [sig(0, "BUY")]
    features = [feat(0, rsi=75.0)]
    result = filter_avoid_extreme_rsi(signals, features)
    assert result[0].direction == "WAIT"


def test_extreme_rsi_filter_suppresses_oversold_sell():
    signals = [sig(0, "SELL")]
    features = [feat(0, rsi=20.0)]
    result = filter_avoid_extreme_rsi(signals, features)
    assert result[0].direction == "WAIT"


def test_extreme_rsi_filter_does_not_suppress_the_asymmetric_case():
    """A BUY at oversold RSI (not overbought) is NOT part of this
    hypothesis and must pass through unaffected."""
    signals = [sig(0, "BUY")]
    features = [feat(0, rsi=20.0)]
    result = filter_avoid_extreme_rsi(signals, features)
    assert result[0].direction == "BUY"


def test_extreme_rsi_filter_passes_through_moderate_rsi():
    signals = [sig(0, "BUY"), sig(1, "SELL")]
    features = [feat(0, rsi=55.0), feat(1, rsi=45.0)]
    result = filter_avoid_extreme_rsi(signals, features)
    assert result[0].direction == "BUY"
    assert result[1].direction == "SELL"


def test_extreme_rsi_filter_handles_none_rsi_by_passing_through():
    """Warm-up period (RSI None) must not crash or be treated as extreme."""
    signals = [sig(0, "BUY")]
    features = [feat(0, rsi=None)]
    result = filter_avoid_extreme_rsi(signals, features)
    assert result[0].direction == "BUY"
