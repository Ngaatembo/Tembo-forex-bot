from datetime import datetime, timedelta, timezone

from app.strategy_engine.crossover import detect_crossover_signals
from app.technical_engine.models import TechnicalFeature

BASE = datetime(2024, 1, 8, 0, 0, tzinfo=timezone.utc)


def feat(hour: int, close: float, sma_10, sma_50) -> TechnicalFeature:
    return TechnicalFeature(timestamp=BASE + timedelta(hours=hour), close=close, sma_10=sma_10, sma_50=sma_50)


def test_all_wait_during_warmup():
    features = [feat(i, 1.09, None, None) for i in range(5)]
    signals = detect_crossover_signals(features, symbol="EUR/USD")
    assert all(s.direction == "WAIT" for s in signals)
    assert all(s.reason.startswith("Insufficient data") for s in signals)


def test_buy_signal_on_upward_cross():
    # fast starts below slow, then crosses above
    features = [
        feat(0, 1.09, 1.090, 1.095),  # below
        feat(1, 1.10, 1.096, 1.095),  # crosses above -> BUY
        feat(2, 1.10, 1.098, 1.095),  # stays above -> WAIT (not a repeat signal)
    ]
    signals = detect_crossover_signals(features, symbol="EUR/USD")
    assert signals[0].direction == "WAIT"  # no prior diff to compare against
    assert signals[1].direction == "BUY"
    assert signals[2].direction == "WAIT"


def test_sell_signal_on_downward_cross():
    features = [
        feat(0, 1.10, 1.098, 1.095),  # above
        feat(1, 1.09, 1.093, 1.095),  # crosses below -> SELL
        feat(2, 1.09, 1.090, 1.095),  # stays below -> WAIT
    ]
    signals = detect_crossover_signals(features, symbol="EUR/USD")
    assert signals[0].direction == "WAIT"
    assert signals[1].direction == "SELL"
    assert signals[2].direction == "WAIT"


def test_no_signal_when_no_crossover_occurs():
    # fast stays above slow the entire time
    features = [feat(i, 1.10, 1.098 + i * 0.0001, 1.095) for i in range(5)]
    signals = detect_crossover_signals(features, symbol="EUR/USD")
    assert all(s.direction == "WAIT" for s in signals)


def test_multiple_crossovers_detected_in_sequence():
    features = [
        feat(0, 1.09, 1.090, 1.095),  # below
        feat(1, 1.10, 1.096, 1.095),  # cross up -> BUY
        feat(2, 1.10, 1.097, 1.095),  # stays above -> WAIT
        feat(3, 1.09, 1.093, 1.095),  # cross down -> SELL
        feat(4, 1.09, 1.090, 1.095),  # stays below -> WAIT
        feat(5, 1.10, 1.096, 1.095),  # cross up again -> BUY
    ]
    signals = detect_crossover_signals(features, symbol="EUR/USD")
    directions = [s.direction for s in signals]
    assert directions == ["WAIT", "BUY", "WAIT", "SELL", "WAIT", "BUY"]


def test_exact_equality_does_not_fire_a_signal_but_updates_state():
    features = [
        feat(0, 1.09, 1.090, 1.095),  # below
        feat(1, 1.095, 1.095, 1.095),  # exactly equal -> WAIT (not a strict cross yet)
        feat(2, 1.10, 1.100, 1.095),  # now strictly above -> BUY (transition from <=0 to >0)
    ]
    signals = detect_crossover_signals(features, symbol="EUR/USD")
    assert signals[0].direction == "WAIT"
    assert signals[1].direction == "WAIT"
    assert signals[2].direction == "BUY"


def test_transition_out_of_warmup_never_fires_a_signal():
    """The very first candle with valid SMAs has no prior diff to compare
    against, so it can never be a BUY/SELL regardless of where the MAs sit."""
    features = [feat(0, 1.09, None, None), feat(1, 1.10, 1.098, 1.095)]
    signals = detect_crossover_signals(features, symbol="EUR/USD")
    assert signals[1].direction == "WAIT"


def test_symbol_is_attached_to_every_signal():
    features = [feat(0, 1.09, 1.090, 1.095), feat(1, 1.10, 1.096, 1.095)]
    signals = detect_crossover_signals(features, symbol="GBP/USD")
    assert all(s.symbol == "GBP/USD" for s in signals)


def test_deterministic_across_runs():
    features = [feat(i, 1.09 + i * 0.001, 1.090 + i * 0.0005, 1.095) for i in range(10)]
    first = detect_crossover_signals(features, symbol="EUR/USD")
    second = detect_crossover_signals(features, symbol="EUR/USD")
    assert [s.direction for s in first] == [s.direction for s in second]


def test_empty_features_returns_empty_signals():
    assert detect_crossover_signals([], symbol="EUR/USD") == []
