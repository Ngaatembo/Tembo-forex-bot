"""
Tests the backtesting engine's execution/portfolio logic directly,
using hand-constructed Candle and Signal lists (same technique Phase 3
used to test crossover logic independent of SMA calculation). This
lets every expected number be verified by hand, not by trusting the
engine's own output.
"""

import pytest
from datetime import datetime, timedelta, timezone

from app.backtesting.config import BacktestConfig
from app.backtesting.engine import simulate_trades
from app.data_engine.market_data import Candle
from app.strategy_engine.models import Signal
from tests.fixtures.backtest_fixtures import trending_candles

BASE = datetime(2024, 1, 8, 0, 0, tzinfo=timezone.utc)


def candle(hour: int, open_: float, close: float) -> Candle:
    ts = BASE + timedelta(hours=hour)
    return Candle(
        symbol="EUR/USD", timeframe="1h", timestamp=ts,
        open=open_, high=max(open_, close) + 0.001, low=min(open_, close) - 0.001,
        close=close, volume=100,
    )


def wait(hour: int) -> Signal:
    return Signal(
        timestamp=BASE + timedelta(hours=hour), symbol="EUR/USD", direction="WAIT",
        sma_10=None, sma_50=None, reason="No crossover on this candle.",
    )


def buy(hour: int) -> Signal:
    return Signal(
        timestamp=BASE + timedelta(hours=hour), symbol="EUR/USD", direction="BUY",
        sma_10=1.0, sma_50=0.9, reason="SMA10 crossed above SMA50.",
    )


def sell(hour: int) -> Signal:
    return Signal(
        timestamp=BASE + timedelta(hours=hour), symbol="EUR/USD", direction="SELL",
        sma_10=0.9, sma_50=1.0, reason="SMA10 crossed below SMA50.",
    )


def test_empty_dataset_handled_safely():
    """Test 1."""
    config = BacktestConfig()
    result = simulate_trades([], [], config)
    assert result.trades == []
    assert result.equity_curve == []
    assert result.summary.trade_count == 0


def test_insufficient_data_produces_no_trades():
    """Test 2 — fewer than 50 candles means SMA50 never becomes valid."""
    from app.backtesting.engine import run_backtest
    candles = trending_candles()[:20]
    result = run_backtest(candles, BacktestConfig())
    assert result.summary.trade_count == 0


def test_bullish_crossover_produces_exactly_one_entry():
    """Tests 3 & 7 — one BUY signal opens exactly one LONG, executed at
    the NEXT candle's open (never the signal candle's own price)."""
    candles = [candle(0, 1.1000, 1.1000), candle(1, 1.1010, 1.1010), candle(2, 1.1020, 1.1020)]
    signals = [buy(0), wait(1), wait(2)]
    config = BacktestConfig(spread=0.0, slippage=0.0)

    result = simulate_trades(candles, signals, config)

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.direction == "LONG"
    assert trade.entry_timestamp == candles[1].timestamp
    assert trade.entry_price == candles[1].open  # not candles[0].close


def test_does_not_stack_a_second_position_on_repeated_signal():
    """Test 4 — even if a duplicate BUY somehow fired, the engine must
    not open a second position on top of an existing one."""
    candles = [candle(i, 1.10 + i * 0.001, 1.10 + i * 0.001) for i in range(4)]
    signals = [buy(0), buy(1), wait(2), wait(3)]
    config = BacktestConfig(spread=0.0, slippage=0.0)

    result = simulate_trades(candles, signals, config)

    assert len(result.trades) == 1  # only one position ever existed


def test_opposite_signal_closes_and_reverses():
    """Test 5 — a SELL after a BUY closes the long and opens a short."""
    candles = [candle(i, 1.10, 1.10) for i in range(4)]
    signals = [buy(0), wait(1), sell(2), wait(3)]
    config = BacktestConfig(spread=0.0, slippage=0.0)

    result = simulate_trades(candles, signals, config)

    assert len(result.trades) == 2
    assert result.trades[0].direction == "LONG"
    assert "Reversed by opposite signal" in result.trades[0].exit_reason
    assert result.trades[1].direction == "SHORT"


def test_multiple_crossovers_in_sequence():
    """Test 15."""
    candles = [candle(i, 1.10, 1.10) for i in range(6)]
    signals = [buy(0), wait(1), sell(2), wait(3), buy(4), wait(5)]
    config = BacktestConfig(spread=0.0, slippage=0.0)

    result = simulate_trades(candles, signals, config)

    directions = [t.direction for t in result.trades]
    assert directions == ["LONG", "SHORT", "LONG"]


def test_earlier_trade_entry_unaffected_by_appending_more_candles():
    """Test 6 — a trade's entry price/timestamp must be identical
    whether or not more (WAIT) candles are appended afterward."""
    candles = [candle(i, 1.10 + i * 0.001, 1.10 + i * 0.001) for i in range(4)]
    signals = [buy(0), wait(1), wait(2), wait(3)]
    config = BacktestConfig(spread=0.0, slippage=0.0)

    short_run = simulate_trades(candles, signals, config)

    extra_candles = candles + [candle(4, 1.20, 1.20), candle(5, 1.21, 1.21)]
    extra_signals = signals + [wait(4), wait(5)]
    long_run = simulate_trades(extra_candles, extra_signals, config)

    assert short_run.trades[0].entry_timestamp == long_run.trades[0].entry_timestamp
    assert short_run.trades[0].entry_price == long_run.trades[0].entry_price


def test_spread_affects_pnl_correctly():
    """Test 8 — hand-verified: gross $50, spread cost $10 round-turn, net $40."""
    candles = [candle(0, 1.1000, 1.1000), candle(1, 1.1000, 1.1000), candle(2, 1.1050, 1.1050)]
    signals = [buy(0), wait(1), wait(2)]
    config = BacktestConfig(spread=0.0010, slippage=0.0, position_size=10_000)

    result = simulate_trades(candles, signals, config)
    trade = result.trades[0]

    assert trade.gross_pnl == pytest.approx(50.0)
    assert trade.transaction_costs == pytest.approx(10.0)
    assert trade.net_pnl == pytest.approx(40.0)


def test_slippage_affects_pnl_correctly():
    """Test 9 — hand-verified: gross $50, slippage cost $4 (2 x 0.0002 x size), net $46."""
    candles = [candle(0, 1.1000, 1.1000), candle(1, 1.1000, 1.1000), candle(2, 1.1050, 1.1050)]
    signals = [buy(0), wait(1), wait(2)]
    config = BacktestConfig(spread=0.0, slippage=0.0002, position_size=10_000)

    result = simulate_trades(candles, signals, config)
    trade = result.trades[0]

    assert trade.gross_pnl == pytest.approx(50.0)
    assert trade.transaction_costs == pytest.approx(4.0)
    assert trade.net_pnl == pytest.approx(46.0)


def test_end_of_data_open_position_is_closed_and_tagged():
    """Test 10."""
    candles = [candle(0, 1.10, 1.10), candle(1, 1.10, 1.10), candle(2, 1.11, 1.11)]
    signals = [buy(0), wait(1), wait(2)]
    config = BacktestConfig(spread=0.0, slippage=0.0)

    result = simulate_trades(candles, signals, config)

    assert len(result.trades) == 1
    assert result.trades[0].exit_reason == "END_OF_DATA"
    assert result.trades[0].exit_timestamp == candles[-1].timestamp


def test_short_trade_pnl_direction_is_correct():
    """Test 11 — a SHORT profits when price falls; hand-verified: $50 gross on a 50-pip drop."""
    candles = [candle(0, 1.1000, 1.1000), candle(1, 1.1000, 1.1000), candle(2, 1.0950, 1.0950)]
    signals = [sell(0), wait(1), wait(2)]
    config = BacktestConfig(spread=0.0, slippage=0.0, position_size=10_000)

    result = simulate_trades(candles, signals, config)
    trade = result.trades[0]

    assert trade.direction == "SHORT"
    assert trade.net_pnl == pytest.approx(50.0)
