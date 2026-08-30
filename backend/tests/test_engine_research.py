import pytest
from datetime import datetime, timedelta, timezone

from app.backtesting.config import BacktestConfig
from app.backtesting.engine import simulate_trades as baseline_simulate_trades
from app.backtesting.engine_research import simulate_trades_with_exit_rules
from app.backtesting.exit_rules import BASELINE_EXIT, ExitConfig
from app.data_engine.market_data import Candle
from app.strategy_engine.models import Signal
from app.technical_engine.models import FeatureSnapshot

BASE = datetime(2024, 1, 8, 0, 0, tzinfo=timezone.utc)


def candle(hour: int, open_: float, high: float, low: float, close: float) -> Candle:
    return Candle(
        symbol="EUR/USD", timeframe="1h", timestamp=BASE + timedelta(hours=hour),
        open=open_, high=high, low=low, close=close, volume=100,
    )


def wait(hour: int) -> Signal:
    return Signal(timestamp=BASE + timedelta(hours=hour), symbol="EUR/USD", direction="WAIT",
                   sma_10=None, sma_50=None, reason="no crossover")


def buy(hour: int) -> Signal:
    return Signal(timestamp=BASE + timedelta(hours=hour), symbol="EUR/USD", direction="BUY",
                   sma_10=1.0, sma_50=0.9, reason="crossed up")


def sell(hour: int) -> Signal:
    return Signal(timestamp=BASE + timedelta(hours=hour), symbol="EUR/USD", direction="SELL",
                   sma_10=0.9, sma_50=1.0, reason="crossed down")


def feat(hour: int, atr: float | None = 0.0010) -> FeatureSnapshot:
    return FeatureSnapshot(
        timestamp=BASE + timedelta(hours=hour), close=1.10,
        sma_10=1.0, sma_50=0.9, sma_50_slope=0.0, sma_distance=0.1, sma_distance_pct=0.09,
        rsi_14=50.0, atr_14=atr, atr_percent=0.001,
        recent_high=1.11, recent_low=1.08, rolling_range=0.03,
        distance_from_high=0.01, distance_from_low=0.02, regime="RANGING",
    )


def test_fixed_stop_loss_triggers_at_exact_price():
    candles = [
        candle(0, 1.1000, 1.1005, 1.0995, 1.1000),  # signal candle
        candle(1, 1.1000, 1.1002, 1.0998, 1.1000),  # entry candle: open=1.1000, stop=1.1000-1.1%=1.0989
        candle(2, 1.0995, 1.0995, 1.0985, 1.0990),  # low 1.0985 breaches stop 1.0989
        candle(3, 1.0990, 1.0995, 1.0988, 1.0992),
    ]
    signals = [buy(0), wait(1), wait(2), wait(3)]
    features = [feat(0), feat(1), feat(2), feat(3)]
    config = BacktestConfig(spread=0.0, slippage=0.0)
    exit_config = ExitConfig(label="fixed_stop_0p1pct", stop_loss_pct=0.001)

    result = simulate_trades_with_exit_rules(candles, signals, features, config, exit_config)

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.exit_reason == "STOP_LOSS"
    expected_stop = 1.1000 - 0.001 * 1.1000
    assert trade.exit_price == pytest.approx(expected_stop)
    assert trade.exit_timestamp == candles[2].timestamp  # triggered on candle 2, not later


def test_fixed_take_profit_triggers_at_exact_price():
    candles = [
        candle(0, 1.1000, 1.1005, 1.0995, 1.1000),
        candle(1, 1.1000, 1.1002, 1.0998, 1.1000),  # entry open=1.1000, target=1.1000+2%=1.1220
        candle(2, 1.1200, 1.1225, 1.1195, 1.1210),  # high 1.1225 breaches target 1.1220
        candle(3, 1.1210, 1.1215, 1.1205, 1.1208),
    ]
    signals = [buy(0), wait(1), wait(2), wait(3)]
    features = [feat(0), feat(1), feat(2), feat(3)]
    config = BacktestConfig(spread=0.0, slippage=0.0)
    exit_config = ExitConfig(label="fixed_tp_2pct", take_profit_pct=0.02)

    result = simulate_trades_with_exit_rules(candles, signals, features, config, exit_config)

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.exit_reason == "TAKE_PROFIT"
    expected_target = 1.1000 + 0.02 * 1.1000
    assert trade.exit_price == pytest.approx(expected_target)


def test_atr_stop_uses_atr_frozen_at_entry_not_recalculated():
    """The ATR at candle 5 is different/larger than at entry (candle 1) —
    the stop distance must reflect entry-time ATR only."""
    candles = [
        candle(0, 1.1000, 1.1005, 1.0995, 1.1000),
        candle(1, 1.1000, 1.1002, 1.0998, 1.1000),  # entry, ATR here = 0.0010 -> stop = 1.1000 - 2*0.0010 = 1.0980
        candle(2, 1.0995, 1.0997, 1.0985, 1.0990),  # low 1.0985 does NOT breach 1.0980
        candle(3, 1.0990, 1.0992, 1.0979, 1.0985),  # low 1.0979 DOES breach 1.0980
    ]
    signals = [buy(0), wait(1), wait(2), wait(3)]
    # entry-candle ATR = 0.0010; a later candle's (unused) ATR is much bigger —
    # if the engine wrongly recalculated, the stop would be much wider and NOT trigger here.
    features = [feat(0, atr=0.0010), feat(1, atr=0.0010), feat(2, atr=0.0050), feat(3, atr=0.0050)]
    config = BacktestConfig(spread=0.0, slippage=0.0)
    exit_config = ExitConfig(label="atr_stop_2x", atr_stop_multiple=2.0)

    result = simulate_trades_with_exit_rules(candles, signals, features, config, exit_config)

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.exit_reason == "STOP_LOSS"
    assert trade.exit_price == pytest.approx(1.1000 - 2 * 0.0010)


def test_max_holding_period_forces_exit_after_n_candles():
    candles = [candle(i, 1.10, 1.101, 1.099, 1.10) for i in range(6)]
    signals = [buy(0)] + [wait(i) for i in range(1, 6)]
    features = [feat(i) for i in range(6)]
    config = BacktestConfig(spread=0.0, slippage=0.0)
    # entry at candle 1 (index 1); max_holding=2 candles -> forced exit once
    # (candle_index - entry_index) >= 2, i.e. at candle index 3
    exit_config = ExitConfig(label="max_hold_2", max_holding_candles=2)

    result = simulate_trades_with_exit_rules(candles, signals, features, config, exit_config)

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.exit_reason == "MAX_HOLDING_PERIOD"
    assert trade.exit_timestamp == candles[3].timestamp


def test_stop_checked_before_opposite_signal_in_same_candle():
    """If both a stop-loss AND a queued reversal signal would act on the
    same candle, the stop must be processed first (position already
    closed by the time the reversal logic runs)."""
    candles = [
        candle(0, 1.1000, 1.1005, 1.0995, 1.1000),  # BUY signal here
        candle(1, 1.1000, 1.1002, 1.0998, 1.1000),  # entry: open=1.1000, stop(1%)=1.0989; SELL signal here too
        candle(2, 1.0985, 1.0990, 1.0980, 1.0985),  # low breaches stop AND this is where the SELL would execute
    ]
    signals = [buy(0), sell(1), wait(2)]
    features = [feat(0), feat(1), feat(2)]
    config = BacktestConfig(spread=0.0, slippage=0.0)
    exit_config = ExitConfig(label="fixed_stop_0p1pct", stop_loss_pct=0.001)

    result = simulate_trades_with_exit_rules(candles, signals, features, config, exit_config)

    # Trade 1: LONG closed by STOP_LOSS at candle 2 (checked first)
    # Trade 2: SHORT opened by the queued SELL signal, same candle's open
    assert len(result.trades) >= 1
    assert result.trades[0].exit_reason == "STOP_LOSS"


def test_baseline_exit_config_matches_phase4_baseline_engine_exactly():
    """Regression cross-check: with no stop/target/holding set, the
    Phase 6 engine must produce IDENTICAL trades to Phase 4's untouched
    simulate_trades() for the same input."""
    candles = [candle(i, 1.10 + i * 0.001, 1.101 + i * 0.001, 1.099 + i * 0.001, 1.10 + i * 0.001) for i in range(6)]
    signals = [buy(0), wait(1), sell(2), wait(3), buy(4), wait(5)]
    features = [feat(i) for i in range(6)]
    config = BacktestConfig(spread=0.0001, slippage=0.00002)

    baseline_result = baseline_simulate_trades(candles, signals, config)
    research_result = simulate_trades_with_exit_rules(candles, signals, features, config, BASELINE_EXIT)

    assert len(baseline_result.trades) == len(research_result.trades)
    for bt, rt in zip(baseline_result.trades, research_result.trades):
        assert bt.direction == rt.direction
        assert bt.entry_price == pytest.approx(rt.entry_price)
        assert bt.exit_price == pytest.approx(rt.exit_price)
        assert bt.net_pnl == pytest.approx(rt.net_pnl)
        assert bt.exit_reason == rt.exit_reason


def test_future_candles_do_not_change_earlier_stop_trigger():
    """Lookahead check specific to the new exit-rule engine."""
    candles = [
        candle(0, 1.1000, 1.1005, 1.0995, 1.1000),
        candle(1, 1.1000, 1.1002, 1.0998, 1.1000),
        candle(2, 1.0995, 1.0997, 1.0985, 1.0990),  # breaches stop here
        candle(3, 1.0990, 1.0995, 1.0988, 1.0992),
    ]
    signals = [buy(0), wait(1), wait(2), wait(3)]
    features = [feat(0), feat(1), feat(2), feat(3)]
    config = BacktestConfig(spread=0.0, slippage=0.0)
    exit_config = ExitConfig(label="fixed_stop_0p1pct", stop_loss_pct=0.001)

    baseline = simulate_trades_with_exit_rules(candles, signals, features, config, exit_config)

    future_candle = candle(4, 5.0, 5.5, 4.5, 5.0)
    future_signal = wait(4)
    future_feature = feat(4)
    extended = simulate_trades_with_exit_rules(
        candles + [future_candle], signals + [future_signal], features + [future_feature],
        config, exit_config,
    )

    assert baseline.trades[0] == extended.trades[0]


def test_mismatched_input_lengths_raise():
    candles = [candle(0, 1.10, 1.101, 1.099, 1.10)]
    with pytest.raises(ValueError):
        simulate_trades_with_exit_rules(candles, [buy(0), wait(1)], [feat(0)], BacktestConfig(), BASELINE_EXIT)


def test_deterministic_across_runs():
    candles = [candle(i, 1.10, 1.102, 1.098, 1.10) for i in range(10)]
    signals = [buy(0)] + [wait(i) for i in range(1, 10)]
    features = [feat(i) for i in range(10)]
    config = BacktestConfig(spread=0.0001, slippage=0.0)
    exit_config = ExitConfig(label="fixed_stop_0p1pct", stop_loss_pct=0.001)

    first = simulate_trades_with_exit_rules(candles, signals, features, config, exit_config)
    second = simulate_trades_with_exit_rules(candles, signals, features, config, exit_config)

    assert [t.net_pnl for t in first.trades] == [t.net_pnl for t in second.trades]


def test_entry_filter_actually_changes_resulting_trades():
    """
    Regression test for a real bug caught during Phase 6: the original
    experiment script called Phase 4's run_backtest() (which recomputes
    its OWN unfiltered signals internally) whenever no exit rule was
    active, silently discarding any entry filter that had been applied.
    This proves the correct wiring: filtering out a BUY signal before
    passing it to simulate_trades_with_exit_rules() must actually change
    the resulting trade list, not produce an identical result to the
    unfiltered baseline.
    """
    from app.strategy_engine.entry_filters import filter_avoid_low_volatility
    from app.technical_engine.models import FeatureSnapshot

    candles = [candle(i, 1.10, 1.101, 1.099, 1.10) for i in range(4)]
    signals = [buy(0), wait(1), wait(2), wait(3)]

    low_vol_feature = FeatureSnapshot(
        timestamp=BASE, close=1.10, sma_10=1.0, sma_50=0.9, sma_50_slope=0.0,
        sma_distance=0.1, sma_distance_pct=0.09, rsi_14=50.0, atr_14=0.0005,
        atr_percent=0.0005, recent_high=1.11, recent_low=1.08, rolling_range=0.03,
        distance_from_high=0.01, distance_from_low=0.02, regime="LOW_VOLATILITY",
    )
    features = [low_vol_feature] + [feat(i) for i in range(1, 4)]

    config = BacktestConfig(spread=0.0, slippage=0.0)

    unfiltered_result = simulate_trades_with_exit_rules(candles, signals, features, config, BASELINE_EXIT)
    assert len(unfiltered_result.trades) == 1  # the BUY at candle 0 opens a position

    filtered_signals = filter_avoid_low_volatility(signals, features)
    filtered_result = simulate_trades_with_exit_rules(candles, filtered_signals, features, config, BASELINE_EXIT)
    assert len(filtered_result.trades) == 0  # suppressed — no entry ever fires
