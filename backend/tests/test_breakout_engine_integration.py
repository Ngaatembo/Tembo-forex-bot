"""
Engine-level tests for the breakout strategy: execution timing (Test D
completion), final-candle handling (Test E), and the Phase 6-mistake
regression test required by Phase 9 spec section 11 — proving signals
are actually threaded into the backtester, not silently discarded.

Reuses the UNMODIFIED Phase 4/6 engine (engine_research.simulate_trades_with_exit_rules)
— no new engine code was written for this strategy, only the entry
signal generator (breakout.py) and exit configuration (existing exit_rules.ExitConfig).
"""

from datetime import datetime, timedelta, timezone

from app.backtesting.config import BacktestConfig
from app.backtesting.engine_research import simulate_trades_with_exit_rules
from app.backtesting.exit_rules import BASELINE_EXIT, ExitConfig
from app.data_engine.market_data import Candle
from app.strategy_engine.breakout import detect_breakout_signals
from app.technical_engine.features import calculate_feature_snapshots

BASE = datetime(2024, 1, 8, tzinfo=timezone.utc)


def candle(hour, open_, high, low, close):
    return Candle(
        symbol="EUR/USD", timeframe="1h", timestamp=BASE + timedelta(hours=hour),
        open=open_, high=high, low=low, close=close, volume=100,
    )


def _build_breakout_scenario():
    """3 flat warm-up candles (lookback=3), then a clean breakout candle."""
    candles = [
        candle(0, 1.10, 1.10, 1.09, 1.10),
        candle(1, 1.10, 1.10, 1.09, 1.10),
        candle(2, 1.10, 1.10, 1.09, 1.10),
        candle(3, 1.10, 1.20, 1.10, 1.20),  # breaks above prior_high (1.10)
        candle(4, 1.21, 1.22, 1.20, 1.21),
        candle(5, 1.21, 1.22, 1.20, 1.21),
    ]
    return candles


def test_D_execution_happens_at_next_candle_open_not_signal_candle():
    """Test D — a breakout detected at candle T executes no earlier than T+1's open."""
    candles = _build_breakout_scenario()
    signals = detect_breakout_signals(candles, lookback=3, symbol="EUR/USD")
    assert signals[3].direction == "BUY"  # confirms the scenario fires where expected

    features = calculate_feature_snapshots(candles)
    config = BacktestConfig(spread=0.0, slippage=0.0)
    result = simulate_trades_with_exit_rules(candles, signals, features, config, BASELINE_EXIT)

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.entry_timestamp == candles[4].timestamp  # T+1, not candles[3]
    assert trade.entry_price == candles[4].open  # candle 4's OPEN, not candle 3's close


def test_E_signal_on_final_candle_never_executes():
    """Test E — a signal with no next candle to execute at must not
    fabricate an execution from nonexistent future data."""
    candles = _build_breakout_scenario()[:4]  # cut right after the breakout candle
    signals = detect_breakout_signals(candles, lookback=3, symbol="EUR/USD")
    assert signals[3].direction == "BUY"  # the breakout signal IS on the final candle

    features = calculate_feature_snapshots(candles)
    config = BacktestConfig(spread=0.0, slippage=0.0)
    result = simulate_trades_with_exit_rules(candles, signals, features, config, BASELINE_EXIT)

    # The BUY signal on the last candle has no T+1 — it must never execute.
    assert len(result.trades) == 0


def test_breakout_signals_actually_reach_the_backtester():
    """
    Phase 9 spec section 11 — the Phase 6-mistake regression test.
    Proves breakout signals are ACTUALLY passed into and respected by
    the engine, not accidentally discarded in favor of an unfiltered/
    empty signal list underneath (the exact class of bug found and
    fixed in Phase 6).
    """
    candles = _build_breakout_scenario()
    real_signals = detect_breakout_signals(candles, lookback=3, symbol="EUR/USD")
    features = calculate_feature_snapshots(candles)
    config = BacktestConfig(spread=0.0, slippage=0.0)

    real_result = simulate_trades_with_exit_rules(candles, real_signals, features, config, BASELINE_EXIT)
    assert len(real_result.trades) == 1  # the real signals produce a real trade

    # An all-WAIT signal list (what a "signals silently discarded" bug
    # would effectively behave like) must produce ZERO trades — proving
    # the engine genuinely depends on the signals it's given, not some
    # other implicit source.
    from app.strategy_engine.models import Signal
    all_wait_signals = [
        Signal(timestamp=c.timestamp, symbol="EUR/USD", direction="WAIT",
               sma_10=None, sma_50=None, reason="test")
        for c in candles
    ]
    empty_result = simulate_trades_with_exit_rules(candles, all_wait_signals, features, config, BASELINE_EXIT)
    assert len(empty_result.trades) == 0
    assert real_result.trades != empty_result.trades


def test_atr_stop_and_max_holding_both_active_simultaneously():
    """Confirms Phase 6's ExitConfig genuinely supports the combined
    ATR-stop + max-holding exit this strategy uses (not mutually exclusive)."""
    config = ExitConfig(label="breakout_exit", atr_stop_multiple=2.0, max_holding_candles=100)
    assert config.atr_stop_multiple == 2.0
    assert config.max_holding_candles == 100  # construction succeeds — no exclusivity conflict
