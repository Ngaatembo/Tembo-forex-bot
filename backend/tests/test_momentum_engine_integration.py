from datetime import datetime, timedelta, timezone

from app.backtesting.config import BacktestConfig
from app.backtesting.engine_research import simulate_trades_with_exit_rules
from app.backtesting.exit_rules import BASELINE_EXIT
from app.data_engine.market_data import Candle
from app.strategy_engine.momentum import detect_momentum_signals
from app.technical_engine.features import calculate_feature_snapshots

BASE = datetime(2024, 1, 8, tzinfo=timezone.utc)


def candle(hour, close):
    return Candle(symbol="EUR/USD", timeframe="1h", timestamp=BASE + timedelta(hours=hour),
                  open=close, high=close + 0.001, low=close - 0.001, close=close, volume=100)


def _rising_scenario():
    closes = [100, 99, 105, 110, 115, 120]  # first valid momentum (idx2) is already positive -> one clean BUY
    return [candle(i, c) for i, c in enumerate(closes)]


def test_execution_at_next_candle_open_not_signal_candle():
    candles = _rising_scenario()
    signals = detect_momentum_signals(candles, lookback=2, symbol="EUR/USD")
    buy_idx = next(i for i, s in enumerate(signals) if s.direction == "BUY")

    features = calculate_feature_snapshots(candles)
    config = BacktestConfig(spread=0.0, slippage=0.0)
    result = simulate_trades_with_exit_rules(candles, signals, features, config, BASELINE_EXIT)

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.entry_timestamp == candles[buy_idx + 1].timestamp
    assert trade.entry_price == candles[buy_idx + 1].open


def test_signal_on_final_candle_never_executes():
    closes = [100, 99, 105]  # single BUY, exactly on the final candle
    candles = [candle(i, c) for i, c in enumerate(closes)]
    signals = detect_momentum_signals(candles, lookback=2, symbol="EUR/USD")
    assert signals[-1].direction == "BUY"

    features = calculate_feature_snapshots(candles)
    config = BacktestConfig(spread=0.0, slippage=0.0)
    result = simulate_trades_with_exit_rules(candles, signals, features, config, BASELINE_EXIT)
    assert len(result.trades) == 0


def test_signals_actually_reach_the_backtester():
    candles = _rising_scenario()
    real_signals = detect_momentum_signals(candles, lookback=2, symbol="EUR/USD")
    features = calculate_feature_snapshots(candles)
    config = BacktestConfig(spread=0.0, slippage=0.0)

    real_result = simulate_trades_with_exit_rules(candles, real_signals, features, config, BASELINE_EXIT)
    assert len(real_result.trades) == 1

    from app.strategy_engine.models import Signal
    all_wait = [Signal(timestamp=c.timestamp, symbol="EUR/USD", direction="WAIT", sma_10=None, sma_50=None, reason="t") for c in candles]
    empty_result = simulate_trades_with_exit_rules(candles, all_wait, features, config, BASELINE_EXIT)
    assert len(empty_result.trades) == 0
