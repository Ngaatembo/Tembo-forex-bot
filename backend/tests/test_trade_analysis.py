import pytest
from datetime import datetime, timedelta, timezone

from app.backtesting.models import Trade
from app.research.trade_analysis import (
    attach_context_to_trades, group_by_regime, group_by_rsi_zone,
)
from app.technical_engine.models import FeatureSnapshot

BASE = datetime(2024, 1, 8, 0, 0, tzinfo=timezone.utc)


def make_trade(trade_id: int, signal_hour: int, net_pnl: float) -> Trade:
    signal_ts = BASE + timedelta(hours=signal_hour)
    entry_ts = signal_ts + timedelta(hours=1)
    return Trade(
        trade_id=trade_id, symbol="EUR/USD", direction="LONG",
        signal_timestamp=signal_ts, entry_timestamp=entry_ts, entry_price=1.10,
        exit_timestamp=entry_ts + timedelta(hours=5), exit_price=1.10 + net_pnl / 10_000,
        size=10_000, gross_pnl=net_pnl, transaction_costs=0.0, net_pnl=net_pnl,
        return_pct=net_pnl / (1.10 * 10_000), entry_reason="test", exit_reason="test",
    )


def make_feature(hour: int, regime: str, rsi: float | None) -> FeatureSnapshot:
    return FeatureSnapshot(
        timestamp=BASE + timedelta(hours=hour), close=1.10,
        sma_10=1.10, sma_50=1.09, sma_50_slope=0.001, sma_distance=0.01, sma_distance_pct=0.009,
        rsi_14=rsi, atr_14=0.001, atr_percent=0.001,
        recent_high=1.11, recent_low=1.08, rolling_range=0.03,
        distance_from_high=0.01, distance_from_low=0.02, regime=regime,
    )


def test_context_attached_at_signal_timestamp_not_entry_timestamp():
    """Critical timing rule (Phase 5 spec section 16)."""
    trade = make_trade(1, signal_hour=5, net_pnl=10.0)
    # A feature snapshot exists at the SIGNAL hour and a DIFFERENT one at
    # entry hour+1 later — must pick the signal-hour one.
    signal_feature = make_feature(5, regime="TRENDING_UP", rsi=60.0)
    entry_feature = make_feature(6, regime="RANGING", rsi=40.0)

    contexts = attach_context_to_trades([trade], [signal_feature, entry_feature])

    assert contexts[0].features.regime == "TRENDING_UP"
    assert contexts[0].features.rsi_14 == 60.0


def test_missing_feature_data_does_not_crash():
    trade = make_trade(1, signal_hour=100, net_pnl=10.0)  # no matching feature timestamp
    contexts = attach_context_to_trades([trade], [make_feature(5, "RANGING", 50.0)])
    assert contexts[0].features is None


def test_group_by_regime_basic_stats():
    trades_and_features = [
        (make_trade(1, 0, 100.0), make_feature(0, "TRENDING_UP", 60.0)),
        (make_trade(2, 1, -30.0), make_feature(1, "TRENDING_UP", 55.0)),
        (make_trade(3, 2, 50.0), make_feature(2, "RANGING", 45.0)),
    ]
    trades = [t for t, f in trades_and_features]
    features = [f for t, f in trades_and_features]
    contexts = attach_context_to_trades(trades, features)

    by_regime = group_by_regime(contexts)

    assert by_regime["TRENDING_UP"].trade_count == 2
    assert by_regime["TRENDING_UP"].winning_trades == 1
    assert by_regime["TRENDING_UP"].losing_trades == 1
    assert by_regime["TRENDING_UP"].net_pnl == pytest.approx(70.0)
    assert by_regime["TRENDING_UP"].win_rate == pytest.approx(0.5)

    assert by_regime["RANGING"].trade_count == 1
    assert by_regime["RANGING"].win_rate == pytest.approx(1.0)


def test_group_by_regime_labels_missing_data_separately():
    trade = make_trade(1, 999, 10.0)  # no matching feature
    contexts = attach_context_to_trades([trade], [])
    by_regime = group_by_regime(contexts)
    assert "NO_FEATURE_DATA" in by_regime
    assert by_regime["NO_FEATURE_DATA"].trade_count == 1


def test_rsi_zone_binning_boundaries():
    trades_and_features = [
        (make_trade(1, 0, 10.0), make_feature(0, "RANGING", 20.0)),   # <30
        (make_trade(2, 1, 10.0), make_feature(1, "RANGING", 45.0)),   # 30-50
        (make_trade(3, 2, 10.0), make_feature(2, "RANGING", 65.0)),   # 50-70
        (make_trade(4, 3, 10.0), make_feature(3, "RANGING", 85.0)),   # >=70
    ]
    trades = [t for t, f in trades_and_features]
    features = [f for t, f in trades_and_features]
    contexts = attach_context_to_trades(trades, features)

    by_rsi = group_by_rsi_zone(contexts)

    assert by_rsi["RSI<30"].trade_count == 1
    assert by_rsi["RSI 30-50"].trade_count == 1
    assert by_rsi["RSI 50-70"].trade_count == 1
    assert by_rsi["RSI>=70"].trade_count == 1


def test_profit_factor_none_with_zero_losses_in_subset():
    trades_and_features = [
        (make_trade(1, 0, 100.0), make_feature(0, "TRENDING_UP", 60.0)),
        (make_trade(2, 1, 50.0), make_feature(1, "TRENDING_UP", 60.0)),
    ]
    trades = [t for t, f in trades_and_features]
    features = [f for t, f in trades_and_features]
    contexts = attach_context_to_trades(trades, features)
    by_regime = group_by_regime(contexts)
    assert by_regime["TRENDING_UP"].profit_factor is None


def test_no_trades_produces_empty_grouping():
    assert group_by_regime([]) == {}
    assert group_by_rsi_zone([]) == {}
