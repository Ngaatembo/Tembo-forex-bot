from datetime import datetime, timedelta, timezone

import pytest

from app.data_engine.market_data import Candle
from app.strategy_engine.momentum import (
    calculate_momentum, detect_confirmed_trend_signals, detect_momentum_signals,
    detect_vol_normalized_signals,
)
from app.technical_engine.models import FeatureSnapshot

BASE = datetime(2024, 1, 8, tzinfo=timezone.utc)


def candle(hour, close, open_=None):
    o = open_ if open_ is not None else close
    return Candle(symbol="EUR/USD", timeframe="1h", timestamp=BASE + timedelta(hours=hour),
                  open=o, high=max(o, close) + 0.001, low=min(o, close) - 0.001, close=close, volume=100)


def feat(hour, atr_percent=0.001):
    return FeatureSnapshot(
        timestamp=BASE + timedelta(hours=hour), close=1.10, sma_10=None, sma_50=None,
        sma_50_slope=None, sma_distance=None, sma_distance_pct=None, rsi_14=None,
        atr_14=None, atr_percent=atr_percent, recent_high=None, recent_low=None,
        rolling_range=None, distance_from_high=None, distance_from_low=None, regime="RANGING",
    )


def test_calculate_momentum_hand_verified():
    closes = [100, 102, 104, 103, 108]
    m = calculate_momentum(closes, lookback=2)
    assert m[0] is None and m[1] is None
    assert m[2] == pytest.approx(104 / 100 - 1)
    assert m[4] == pytest.approx(108 / 104 - 1)


def test_momentum_rejects_invalid_lookback():
    with pytest.raises(ValueError):
        calculate_momentum([1.0], lookback=0)


def test_momentum_does_not_use_future_values():
    closes = [100, 101, 102, 103, 104, 105]
    without_future = calculate_momentum(closes, lookback=2)
    with_future = calculate_momentum(closes + [5000, 6000], lookback=2)
    assert without_future[2] == with_future[2]
    assert without_future[5] == with_future[5]


def test_t1_edge_triggered_not_repeated():
    closes = [100, 99, 98, 105, 110, 115]  # down, down, then sustained up
    candles = [candle(i, c) for i, c in enumerate(closes)]
    signals = detect_momentum_signals(candles, lookback=2, symbol="EUR/USD")
    directions = [s.direction for s in signals]
    buy_count = sum(1 for d in directions if d == "BUY")
    assert buy_count == 1  # fires once on the transition to positive, not every candle after


def test_t1_future_spike_does_not_change_earlier_signals():
    closes = [100, 99, 98, 105, 110]
    candles = [candle(i, c) for i, c in enumerate(closes)]
    baseline = detect_momentum_signals(candles, lookback=2, symbol="EUR/USD")

    extended_closes = closes + [9999]
    extended_candles = [candle(i, c) for i, c in enumerate(extended_closes)]
    extended = detect_momentum_signals(extended_candles, lookback=2, symbol="EUR/USD")

    for i in range(len(candles)):
        assert baseline[i].direction == extended[i].direction


def test_t1_warmup_is_wait():
    closes = [100, 101, 102]
    candles = [candle(i, c) for i, c in enumerate(closes)]
    signals = detect_momentum_signals(candles, lookback=5, symbol="EUR/USD")
    assert all(s.direction == "WAIT" for s in signals)


def test_t2_requires_threshold_to_qualify():
    closes = [100.0, 100.0, 100.1]
    candles = [candle(i, c) for i, c in enumerate(closes)]
    features = [feat(i, atr_percent=0.05) for i in range(3)]
    signals = detect_vol_normalized_signals(candles, features, lookback=2, threshold=1.0, symbol="EUR/USD")
    assert all(s.direction == "WAIT" for s in signals)


def test_t2_qualifying_move_fires():
    closes = [100.0, 100.0, 110.0]
    candles = [candle(i, c) for i, c in enumerate(closes)]
    features = [feat(i, atr_percent=0.001) for i in range(3)]
    signals = detect_vol_normalized_signals(candles, features, lookback=2, threshold=1.0, symbol="EUR/USD")
    assert signals[2].direction == "BUY"


def test_t3_requires_both_lookbacks_to_agree():
    closes = [100, 101, 102, 103, 104, 103, 102]
    candles = [candle(i, c) for i, c in enumerate(closes)]
    signals = detect_confirmed_trend_signals(candles, primary_lookback=6, secondary_lookback=2, symbol="EUR/USD")
    assert signals[-1].direction == "WAIT"


def test_t3_agreement_fires_buy():
    closes = [100, 99, 98, 97, 100, 105, 110]
    candles = [candle(i, c) for i, c in enumerate(closes)]
    signals = detect_confirmed_trend_signals(candles, primary_lookback=4, secondary_lookback=2, symbol="EUR/USD")
    assert any(s.direction == "BUY" for s in signals)


def test_empty_candles_all_generators():
    assert detect_momentum_signals([], 20, "EUR/USD") == []
    assert detect_vol_normalized_signals([], [], 20, 1.0, "EUR/USD") == []
    assert detect_confirmed_trend_signals([], 20, 5, "EUR/USD") == []
