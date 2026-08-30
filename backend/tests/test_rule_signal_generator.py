from datetime import datetime, timedelta, timezone

import pytest

from app.data_engine.market_data import Candle
from app.research.hypothesis import Condition, Hypothesis, HypothesisType, RuleSet
from app.research.rule_signal_generator import generate_signals_from_hypothesis
from app.technical_engine.models import FeatureSnapshot

BASE = datetime(2024, 1, 8, tzinfo=timezone.utc)


def candle(hour: int) -> Candle:
    return Candle(
        symbol="EUR/USD", timeframe="1h", timestamp=BASE + timedelta(hours=hour),
        open=1.10, high=1.101, low=1.099, close=1.10, volume=100,
    )


def feat(hour: int, rsi: float | None) -> FeatureSnapshot:
    return FeatureSnapshot(
        timestamp=BASE + timedelta(hours=hour), close=1.10, sma_10=1.10, sma_50=1.09,
        sma_50_slope=0.001, sma_distance=0.01, sma_distance_pct=0.009, rsi_14=rsi,
        atr_14=0.001, atr_percent=0.001, recent_high=1.11, recent_low=1.08, rolling_range=0.03,
        distance_from_high=0.01, distance_from_low=0.02, regime="RANGING",
    )


def momentum_hypothesis() -> Hypothesis:
    return Hypothesis(
        id="mom_test", name="Momentum Test", description="d", hypothesis_type=HypothesisType.MOMENTUM,
        market="EUR/USD", timeframe="1h",
        entry_long=RuleSet(conditions=(Condition(field="rsi_14", operator=">", value=60.0),)),
        entry_short=RuleSet(conditions=(Condition(field="rsi_14", operator="<", value=40.0),)),
        risk_conditions={}, rationale="r", data_requirements=("rsi_14",),
    )


def test_buy_fires_only_on_transition_into_true():
    candles = [candle(i) for i in range(4)]
    features = [feat(0, 50.0), feat(1, 65.0), feat(2, 66.0), feat(3, 67.0)]  # crosses above 60 at index 1, stays above
    signals = generate_signals_from_hypothesis(momentum_hypothesis(), candles, features)
    directions = [s.direction for s in signals]
    assert directions == ["WAIT", "BUY", "WAIT", "WAIT"]


def test_sell_fires_only_on_transition_into_true():
    candles = [candle(i) for i in range(3)]
    features = [feat(0, 50.0), feat(1, 35.0), feat(2, 30.0)]
    signals = generate_signals_from_hypothesis(momentum_hypothesis(), candles, features)
    directions = [s.direction for s in signals]
    assert directions == ["WAIT", "SELL", "WAIT"]


def test_warmup_produces_wait_not_crash():
    candles = [candle(i) for i in range(2)]
    features = [feat(0, None), feat(1, None)]
    signals = generate_signals_from_hypothesis(momentum_hypothesis(), candles, features)
    assert all(s.direction == "WAIT" for s in signals)


def test_mismatched_lengths_raises():
    candles = [candle(0), candle(1)]
    features = [feat(0, 50.0)]
    with pytest.raises(ValueError):
        generate_signals_from_hypothesis(momentum_hypothesis(), candles, features)


def test_signals_aligned_by_timestamp():
    candles = [candle(i) for i in range(3)]
    features = [feat(0, 50.0), feat(1, 65.0), feat(2, 50.0)]
    signals = generate_signals_from_hypothesis(momentum_hypothesis(), candles, features)
    for c, s in zip(candles, signals):
        assert c.timestamp == s.timestamp
