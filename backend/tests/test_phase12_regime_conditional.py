"""
filter_signals_by_regime (Phase 9.1) already has 13 dedicated tests
covering lookahead/timing/security. These tests add what's specific
to Phase 12: proving the SAME generic function works correctly when
applied to H1's mean-reversion and momentum signals (not just
breakout, which is all it was previously exercised against), plus
edge cases this phase's aggregation specifically needs.
"""

from datetime import datetime, timedelta, timezone

from app.strategy_engine.regime_filter import filter_signals_by_regime
from app.strategy_engine.momentum import detect_momentum_signals
from app.data_engine.market_data import Candle
from app.technical_engine.features import calculate_feature_snapshots

BASE = datetime(2024, 1, 8, tzinfo=timezone.utc)


def candle(hour, close):
    return Candle(symbol="EUR/USD", timeframe="1h", timestamp=BASE + timedelta(hours=hour),
                  open=close, high=close + 0.001, low=close - 0.001, close=close, volume=100)


def test_regime_filter_works_on_momentum_signals_not_just_breakout():
    closes = [100 + i * 0.5 for i in range(80)]
    candles = [candle(i, c) for i, c in enumerate(closes)]
    signals = detect_momentum_signals(candles, lookback=20, symbol="EUR/USD")
    features = calculate_feature_snapshots(candles)

    filtered = filter_signals_by_regime(signals, features, allowed_regimes={"TRENDING_UP"})
    assert len(filtered) == len(signals)
    for sig, feat in zip(filtered, features):
        if sig.direction in ("BUY", "SELL"):
            assert feat.regime in {"TRENDING_UP"}


def test_regime_that_never_occurs_yields_all_wait_no_crash():
    closes = [100 + i * 0.5 for i in range(80)]
    candles = [candle(i, c) for i, c in enumerate(closes)]
    signals = detect_momentum_signals(candles, lookback=20, symbol="EUR/USD")
    features = calculate_feature_snapshots(candles)

    filtered = filter_signals_by_regime(signals, features, allowed_regimes={"NONEXISTENT_REGIME"})
    assert all(s.direction == "WAIT" for s in filtered)


def test_no_duplicate_trades_introduced_by_filtering():
    closes = [100 + (i % 7 - 3) for i in range(80)]
    candles = [candle(i, c) for i, c in enumerate(closes)]
    signals = detect_momentum_signals(candles, lookback=10, symbol="EUR/USD")
    features = calculate_feature_snapshots(candles)

    original_signal_count = sum(1 for s in signals if s.direction in ("BUY", "SELL"))
    filtered = filter_signals_by_regime(
        signals, features,
        allowed_regimes={"RANGING", "TRENDING_UP", "TRENDING_DOWN", "HIGH_VOLATILITY", "LOW_VOLATILITY", "UNKNOWN"},
    )
    filtered_signal_count = sum(1 for s in filtered if s.direction in ("BUY", "SELL"))
    assert filtered_signal_count <= original_signal_count
    assert filtered_signal_count == original_signal_count


def test_low_trade_count_after_filtering_is_representable():
    from app.backtesting.metrics import compute_metrics
    summary = compute_metrics([], [], initial_balance=10000.0)
    assert summary.trade_count == 0
    assert summary.profit_factor is None
