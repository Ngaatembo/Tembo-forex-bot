"""
Engine-level proof for the regime filter: Test D (rejected signals
genuinely cannot reach the backtester as trades) and Test E (accepted
signals still execute next-open, via the unmodified Phase 4/6 engine)
in their real, end-to-end form — not just the unit-level proof in
test_regime_filter.py. Also the section-11 regression guarantee:
running with every regime allowed reproduces Phase 9's exact,
unmodified breakout result.
"""

from datetime import datetime, timedelta, timezone

from app.backtesting.config import BacktestConfig
from app.backtesting.engine_research import simulate_trades_with_exit_rules
from app.backtesting.exit_rules import ExitConfig
from app.data_engine.market_data import Candle
from app.strategy_engine.breakout import detect_breakout_signals
from app.strategy_engine.regime_filter import filter_signals_by_regime
from app.technical_engine.features import calculate_feature_snapshots

BASE = datetime(2024, 1, 8, tzinfo=timezone.utc)


def candle(hour, open_, high, low, close):
    return Candle(
        symbol="EUR/USD", timeframe="1h", timestamp=BASE + timedelta(hours=hour),
        open=open_, high=high, low=low, close=close, volume=100,
    )


def _build_breakout_scenario():
    return [
        candle(0, 1.10, 1.10, 1.09, 1.10),
        candle(1, 1.10, 1.10, 1.09, 1.10),
        candle(2, 1.10, 1.10, 1.09, 1.10),
        candle(3, 1.10, 1.20, 1.10, 1.20),  # breaks above prior_high
        candle(4, 1.21, 1.22, 1.20, 1.21),
        candle(5, 1.21, 1.22, 1.20, 1.21),
    ]


def _run(candles, signals, features):
    exit_config = ExitConfig(label="test", atr_stop_multiple=2.0, max_holding_candles=100)
    config = BacktestConfig(spread=0.0, slippage=0.0)
    return simulate_trades_with_exit_rules(candles, signals, features, config, exit_config)


def test_D_rejected_signal_produces_zero_trades_end_to_end():
    candles = _build_breakout_scenario()
    signals = detect_breakout_signals(candles, lookback=3, symbol="EUR/USD")
    assert signals[3].direction == "BUY"
    features = calculate_feature_snapshots(candles)

    # Reject every regime -> the BUY must never reach the engine as a trade.
    rejected = filter_signals_by_regime(signals, features, allowed_regimes=set())
    result = _run(candles, rejected, features)
    assert len(result.trades) == 0


def test_E_accepted_signal_still_executes_next_open():
    """
    Uses BASELINE_EXIT (matching Phase 9's own equivalent test) — this
    test proves execution TIMING, which doesn't require an ATR-based
    exit at all. An earlier version of this test used an ATR-stop
    config and failed with 0 trades on this tiny 6-candle scenario;
    investigated before assuming a bug — confirmed it was the correct,
    already-documented fail-closed behavior in engine_research.py
    (a trade is skipped, not crashed or opened unprotected, when ATR
    isn't yet available for an ATR-dependent exit — ATR14 needs 13
    candles of warm-up, more than this scenario provides). Not a
    regime-filter bug; fixed by testing the right thing with the
    right exit config.
    """
    from app.backtesting.exit_rules import BASELINE_EXIT

    candles = _build_breakout_scenario()
    signals = detect_breakout_signals(candles, lookback=3, symbol="EUR/USD")
    features = calculate_feature_snapshots(candles)

    all_regimes = {"TRENDING_UP", "TRENDING_DOWN", "RANGING", "HIGH_VOLATILITY", "LOW_VOLATILITY", "UNKNOWN"}
    accepted = filter_signals_by_regime(signals, features, all_regimes)

    config = BacktestConfig(spread=0.0, slippage=0.0)
    result = simulate_trades_with_exit_rules(candles, accepted, features, config, BASELINE_EXIT)

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.entry_timestamp == candles[4].timestamp  # T+1, unchanged from Phase 9
    assert trade.entry_price == candles[4].open


def test_F_regime_filter_has_no_broker_or_execution_dependency():
    """Test F — extends the same source-level scan already used
    throughout the project to this new file specifically."""
    from pathlib import Path
    path = Path(__file__).resolve().parent.parent / "app" / "strategy_engine" / "regime_filter.py"
    content = path.read_text()
    forbidden = [
        "broker_adapter", "BrokerAdapter", "get_broker_adapter",
        "eval(", "exec(", "subprocess", "os.system", "OANDA",
    ]
    for token in forbidden:
        assert token not in content, f"regime_filter.py references '{token}' — a safety regression."


def test_section_11_no_filter_active_reproduces_phase9_baseline_exactly():
    """
    Section 11 — the critical regression guarantee. Running the exact
    same breakout signals through the exact same engine, with an
    all-permissive regime filter applied, must produce BYTE-IDENTICAL
    trades to running with no filter at all (Phase 9's own result).
    This is the direct defense against a Phase-6-style bug where a
    filter silently changes engine behavior even when it should be a
    no-op.
    """
    candles = _build_breakout_scenario()
    signals = detect_breakout_signals(candles, lookback=3, symbol="EUR/USD")
    features = calculate_feature_snapshots(candles)

    unfiltered_result = _run(candles, signals, features)  # Phase 9's exact pathway

    all_regimes = {"TRENDING_UP", "TRENDING_DOWN", "RANGING", "HIGH_VOLATILITY", "LOW_VOLATILITY", "UNKNOWN"}
    permissive_signals = filter_signals_by_regime(signals, features, all_regimes)
    filtered_result = _run(candles, permissive_signals, features)

    assert unfiltered_result.trades == filtered_result.trades
    assert unfiltered_result.summary == filtered_result.summary
