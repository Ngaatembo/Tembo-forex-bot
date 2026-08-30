from datetime import datetime, timedelta, timezone

import pytest

from app.strategy_engine.models import Signal
from app.strategy_engine.regime_filter import filter_signals_by_regime
from app.technical_engine.models import FeatureSnapshot

BASE = datetime(2024, 1, 8, tzinfo=timezone.utc)


def feat(hour: int, regime: str) -> FeatureSnapshot:
    return FeatureSnapshot(
        timestamp=BASE + timedelta(hours=hour), close=1.10,
        sma_10=1.10, sma_50=1.09, sma_50_slope=0.001, sma_distance=0.01, sma_distance_pct=0.009,
        rsi_14=50.0, atr_14=0.001, atr_percent=0.001,
        recent_high=1.11, recent_low=1.08, rolling_range=0.03,
        distance_from_high=0.01, distance_from_low=0.02, regime=regime,
    )


def sig(hour: int, direction: str) -> Signal:
    return Signal(
        timestamp=BASE + timedelta(hours=hour), symbol="EUR/USD", direction=direction,
        sma_10=None, sma_50=None, reason="test",
    )


def test_A_uses_signal_time_regime_only():
    """Test A — the filter decision uses the SAME index's regime as the signal."""
    signals = [sig(0, "BUY"), sig(1, "WAIT"), sig(2, "SELL")]
    features = [feat(0, "TRENDING_UP"), feat(1, "RANGING"), feat(2, "RANGING")]

    result = filter_signals_by_regime(signals, features, {"TRENDING_UP", "TRENDING_DOWN"})

    assert result[0].direction == "BUY"  # regime at index 0 (TRENDING_UP) is allowed
    assert result[2].direction == "WAIT"  # regime at index 2 (RANGING) is not allowed -> suppressed


def test_B_future_price_spike_does_not_change_earlier_filter_decisions():
    """Test B — appending extreme future signals/features must not
    alter any earlier accept/reject decision."""
    signals = [sig(0, "BUY"), sig(1, "WAIT"), sig(2, "SELL")]
    features = [feat(0, "TRENDING_UP"), feat(1, "RANGING"), feat(2, "TRENDING_DOWN")]
    baseline = filter_signals_by_regime(signals, features, {"TRENDING_UP", "TRENDING_DOWN"})

    extended_signals = signals + [sig(100, "BUY")]
    extended_features = features + [feat(100, "HIGH_VOLATILITY")]
    extended = filter_signals_by_regime(extended_signals, extended_features, {"TRENDING_UP", "TRENDING_DOWN"})

    for i in range(len(signals)):
        assert baseline[i].direction == extended[i].direction


def test_C_regime_transition_after_signal_cannot_retroactively_change_decision():
    """
    Test C — a signal accepted (or rejected) at candle T stays that way
    even if the regime at T+1 is completely different. Proven directly:
    the filter never even looks at index i+1 when deciding index i.
    """
    signals = [sig(0, "BUY"), sig(1, "WAIT")]
    # regime at signal time (index 0) is allowed; regime "changes" at index 1
    # (a different candle entirely) — must not affect index 0's decision.
    features_a = [feat(0, "TRENDING_UP"), feat(1, "RANGING")]
    features_b = [feat(0, "TRENDING_UP"), feat(1, "HIGH_VOLATILITY")]  # only index 1 differs

    result_a = filter_signals_by_regime(signals, features_a, {"TRENDING_UP"})
    result_b = filter_signals_by_regime(signals, features_b, {"TRENDING_UP"})

    assert result_a[0].direction == result_b[0].direction == "BUY"


def test_D_rejected_signals_become_wait_not_dropped():
    """
    Test D — a rejected signal becomes WAIT (never reaches the
    backtesting engine as a BUY/SELL); it is never silently removed
    from the list either (same length preserved).
    """
    signals = [sig(0, "BUY")]
    features = [feat(0, "RANGING")]
    result = filter_signals_by_regime(signals, features, {"TRENDING_UP"})

    assert len(result) == 1
    assert result[0].direction == "WAIT"


def test_E_accepted_signal_shape_unchanged_for_downstream_next_open_execution():
    """
    Test E — an accepted signal is passed through with its ORIGINAL
    timestamp intact, so the existing engine's next-open execution
    model (Phase 4/6, unmodified) still applies identically.
    """
    signals = [sig(5, "BUY")]
    features = [feat(5, "TRENDING_UP")]
    result = filter_signals_by_regime(signals, features, {"TRENDING_UP"})

    assert result[0].direction == "BUY"
    assert result[0].timestamp == signals[0].timestamp


def test_no_filter_active_reproduces_original_signals_exactly():
    """
    Section 11 — 'no regime filter active = exactly the Phase 9
    baseline.' Modeled as: every regime is in the allowed set (an
    all-permissive filter) must reproduce the original signal list
    byte-for-byte, since nothing gets suppressed.
    """
    signals = [sig(0, "BUY"), sig(1, "WAIT"), sig(2, "SELL"), sig(3, "WAIT")]
    features = [feat(0, "TRENDING_UP"), feat(1, "RANGING"), feat(2, "HIGH_VOLATILITY"), feat(3, "LOW_VOLATILITY")]
    all_regimes = {"TRENDING_UP", "TRENDING_DOWN", "RANGING", "HIGH_VOLATILITY", "LOW_VOLATILITY", "UNKNOWN"}

    result = filter_signals_by_regime(signals, features, all_regimes)

    for original, filtered in zip(signals, result):
        assert original.direction == filtered.direction
        assert original.timestamp == filtered.timestamp
        assert original.reason == filtered.reason  # unmodified signals pass through untouched


def test_mismatched_lengths_rejected():
    with pytest.raises(ValueError):
        filter_signals_by_regime([sig(0, "BUY")], [], {"TRENDING_UP"})


def test_empty_input_returns_empty():
    assert filter_signals_by_regime([], [], {"TRENDING_UP"}) == []


def test_unknown_regime_always_suppressed_unless_explicitly_allowed():
    signals = [sig(0, "BUY")]
    features = [feat(0, "UNKNOWN")]
    result = filter_signals_by_regime(signals, features, {"TRENDING_UP", "TRENDING_DOWN"})
    assert result[0].direction == "WAIT"
