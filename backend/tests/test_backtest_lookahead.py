"""
Test 21 — the explicit lookahead-bias regression test.

Runs the full real pipeline (technical_engine -> strategy_engine ->
backtesting engine) on a truncated dataset, then again on the same
data with an absurd future price spike appended, and verifies every
trade/equity point computed BEFORE the truncation point is identical
either way.

One documented exception: if the truncated (baseline) run ends with an
open position, the end-of-data policy forces it closed at the final
candle — an artifact of where the dataset happens to stop, not
something the extended run also does at that same point (it has more
data and closes the position later, for a different reason). That one
trade/equity point is excluded from the comparison, explicitly, rather
than silently.
"""

from app.backtesting.config import BacktestConfig
from app.backtesting.engine import run_backtest
from tests.fixtures.backtest_fixtures import extreme_future_candles, trending_candles


def test_appending_future_candles_does_not_change_completed_history():
    candles = trending_candles()
    cutoff = 100  # deliberately inside the "fall" phase — a position is open at this point

    config = BacktestConfig(spread=0.0001, slippage=0.0)

    baseline = run_backtest(candles[:cutoff], config)
    extended = run_backtest(candles[:cutoff] + extreme_future_candles(), config)

    baseline_trades = baseline.trades
    if baseline_trades and baseline_trades[-1].exit_reason == "END_OF_DATA":
        # This closure only happened because the dataset stopped here —
        # exclude it, since the extended run legitimately does NOT close
        # at this point (it has real future data to keep evaluating).
        baseline_trades = baseline_trades[:-1]

    assert len(baseline_trades) > 0, "test fixture must produce at least one completed trade before cutoff"
    assert extended.trades[: len(baseline_trades)] == baseline_trades

    # Equity curve up to (but not including) the final forced-closure
    # point must also be untouched by data that didn't exist yet.
    assert baseline.equity_curve[:-1] == extended.equity_curve[: cutoff - 1]
