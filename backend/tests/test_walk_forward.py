"""
Tests for the walk-forward validation orchestrator. Written before
implementation, per instruction.

Uses tiny synthetic Candle lists and deterministic fake "candidate"
functions (no real strategy_engine dependency needed to test the
orchestrator's own window/selection/aggregation logic in isolation —
matches the same technique test_backtest_engine.py already uses for
constructing Signal lists directly).
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.backtesting.config import BacktestConfig
from app.backtesting.models import BacktestResult, BacktestSummary
from app.data_engine.market_data import Candle
from app.research.walk_forward import (
    InsufficientDataError, WalkForwardConfig, generate_walk_forward_windows, run_walk_forward,
)

_START = datetime(2020, 1, 1, tzinfo=timezone.utc)


def make_candles(n_days: int, start: datetime = _START) -> list[Candle]:
    return [
        Candle(
            symbol="EUR/USD", timeframe="d1", timestamp=start + timedelta(days=i),
            open=1.10, high=1.11, low=1.09, close=1.10, volume=None,
        )
        for i in range(n_days)
    ]


def _empty_summary(initial_balance: float = 1000.0) -> BacktestSummary:
    return BacktestSummary(initial_balance=initial_balance, final_balance=initial_balance, net_pnl=0.0, total_return=0.0, trade_count=0)


def _summary_with_trades(trade_count: int, profit_factor: float, win_rate: float = 0.5, expectancy: float = 1.0, max_dd: float = 5.0) -> BacktestSummary:
    return BacktestSummary(
        initial_balance=1000.0, final_balance=1000.0 + trade_count * expectancy, net_pnl=trade_count * expectancy,
        total_return=0.01, trade_count=trade_count, winning_trades=int(trade_count * win_rate),
        losing_trades=trade_count - int(trade_count * win_rate), win_rate=win_rate, average_win=2.0,
        average_loss=-1.0, largest_win=3.0, largest_loss=-2.0, average_trade=expectancy, expectancy=expectancy,
        max_consecutive_wins=2, max_consecutive_losses=1, profit_factor=profit_factor,
        max_drawdown=max_dd, max_drawdown_percent=0.5,
    )


def make_fake_runner(trade_count: int, profit_factor: float, config: BacktestConfig, label: str = "candidate"):
    def _runner(candles: list[Candle], cfg: BacktestConfig) -> BacktestResult:
        summary = _summary_with_trades(trade_count, profit_factor) if candles else _empty_summary()
        return BacktestResult(configuration=cfg, summary=summary, trades=[], equity_curve=[])
    return _runner


def test_windows_are_strictly_chronological():
    config = WalkForwardConfig(development_days=30, validation_days=10, out_of_sample_days=10, step_days=10)
    candles = make_candles(100)
    windows = generate_walk_forward_windows(candles, config)
    assert len(windows) >= 1
    for w in windows:
        assert w.periods.development.start < w.periods.development.end
        assert w.periods.development.end <= w.periods.validation.start
        assert w.periods.validation.end <= w.periods.out_of_sample.start


def test_windows_roll_forward_by_step_days():
    config = WalkForwardConfig(development_days=30, validation_days=10, out_of_sample_days=10, step_days=10)
    candles = make_candles(100)
    windows = generate_walk_forward_windows(candles, config)
    assert len(windows) >= 2
    assert windows[1].periods.development.start == windows[0].periods.development.start + timedelta(days=10)


def test_no_overlap_between_dev_validation_oos_within_a_window():
    config = WalkForwardConfig(development_days=20, validation_days=5, out_of_sample_days=5, step_days=5)
    candles = make_candles(60)
    windows = generate_walk_forward_windows(candles, config)
    for w in windows:
        p = w.periods
        assert p.development.end <= p.validation.start
        assert p.validation.end <= p.out_of_sample.start


def test_insufficient_data_raises_explicit_error_not_silent_empty_result():
    config = WalkForwardConfig(development_days=100, validation_days=50, out_of_sample_days=50, step_days=10)
    candles = make_candles(30)
    with pytest.raises(InsufficientDataError):
        generate_walk_forward_windows(candles, config)


def test_exact_fit_produces_exactly_one_window():
    config = WalkForwardConfig(development_days=10, validation_days=5, out_of_sample_days=5, step_days=5)
    candles = make_candles(20)
    windows = generate_walk_forward_windows(candles, config)
    assert len(windows) == 1


def test_selection_uses_only_development_and_validation_candles():
    config = WalkForwardConfig(development_days=20, validation_days=5, out_of_sample_days=5, step_days=5)
    candles = make_candles(30)
    windows = generate_walk_forward_windows(candles, config)
    window = windows[0]

    calls = []

    def spy_runner(candles_seen, cfg):
        oos_ts_in_this_call = {
            c.timestamp for c in candles_seen
            if window.periods.out_of_sample.start <= c.timestamp < window.periods.out_of_sample.end
        }
        calls.append(oos_ts_in_this_call)
        return BacktestResult(configuration=cfg, summary=_summary_with_trades(5, 1.5), trades=[], equity_curve=[])

    bt_config = BacktestConfig(symbol="EUR/USD", timeframe="d1")
    run_walk_forward(candles, [windows[0]], {"only_candidate": spy_runner}, bt_config)
    # First call is the SELECTION call -- must see zero OOS timestamps.
    # A later call (the actual OOS run of the winning candidate) is
    # expected to see OOS data -- that's the point of walk-forward.
    assert len(calls) == 2, "expected exactly one selection call + one OOS run call"
    assert len(calls[0]) == 0, "OOS candles were visible during the SELECTION call -- data leakage."
    assert len(calls[1]) == 5, "the actual OOS run should see exactly the 5 OOS-window candles."


def test_oos_result_never_feeds_back_into_selection_across_windows():
    config = WalkForwardConfig(development_days=10, validation_days=5, out_of_sample_days=5, step_days=5)
    candles = make_candles(20)
    windows = generate_walk_forward_windows(candles, config)
    bt_config = BacktestConfig(symbol="EUR/USD", timeframe="d1")

    candidates = {
        "candidate_a": make_fake_runner(10, profit_factor=2.0, config=bt_config),
        "candidate_b": make_fake_runner(10, profit_factor=1.1, config=bt_config),
    }
    report = run_walk_forward(candles, windows, candidates, bt_config)
    assert report.window_results[0].selected_candidate == "candidate_a"


def test_repeated_runs_are_deterministic():
    config = WalkForwardConfig(development_days=20, validation_days=5, out_of_sample_days=5, step_days=5)
    candles = make_candles(30)
    windows = generate_walk_forward_windows(candles, config)
    bt_config = BacktestConfig(symbol="EUR/USD", timeframe="d1")
    candidates = {
        "a": make_fake_runner(8, profit_factor=1.8, config=bt_config),
        "b": make_fake_runner(8, profit_factor=1.2, config=bt_config),
    }
    report1 = run_walk_forward(candles, windows, candidates, bt_config)
    report2 = run_walk_forward(candles, windows, candidates, bt_config)
    assert [w.selected_candidate for w in report1.window_results] == [w.selected_candidate for w in report2.window_results]
    assert report1.aggregate.total_oos_trades == report2.aggregate.total_oos_trades


def test_ties_broken_by_candidate_dict_order_deterministically():
    config = WalkForwardConfig(development_days=10, validation_days=5, out_of_sample_days=5, step_days=5)
    candles = make_candles(20)
    windows = generate_walk_forward_windows(candles, config)
    bt_config = BacktestConfig(symbol="EUR/USD", timeframe="d1")
    candidates = {
        "first": make_fake_runner(5, profit_factor=1.5, config=bt_config),
        "second": make_fake_runner(5, profit_factor=1.5, config=bt_config),
    }
    report = run_walk_forward(candles, windows, candidates, bt_config)
    assert report.window_results[0].selected_candidate == "first"


def test_candidate_with_zero_validation_trades_is_excluded_from_selection():
    config = WalkForwardConfig(development_days=10, validation_days=5, out_of_sample_days=5, step_days=5)
    candles = make_candles(20)
    windows = generate_walk_forward_windows(candles, config)
    bt_config = BacktestConfig(symbol="EUR/USD", timeframe="d1")
    candidates = {
        "silent": make_fake_runner(0, profit_factor=0.0, config=bt_config),
        "active": make_fake_runner(3, profit_factor=1.3, config=bt_config),
    }
    report = run_walk_forward(candles, windows, candidates, bt_config)
    assert report.window_results[0].selected_candidate == "active"


def test_all_candidates_with_zero_trades_yields_no_selection_for_that_window():
    config = WalkForwardConfig(development_days=10, validation_days=5, out_of_sample_days=5, step_days=5)
    candles = make_candles(20)
    windows = generate_walk_forward_windows(candles, config)
    bt_config = BacktestConfig(symbol="EUR/USD", timeframe="d1")
    candidates = {"a": make_fake_runner(0, profit_factor=0.0, config=bt_config)}
    report = run_walk_forward(candles, windows, candidates, bt_config)
    assert report.window_results[0].selected_candidate is None
    assert report.window_results[0].oos_result is None


def test_aggregate_uses_only_oos_results():
    config = WalkForwardConfig(development_days=10, validation_days=5, out_of_sample_days=5, step_days=5)
    candles = make_candles(30)
    windows = generate_walk_forward_windows(candles, config)
    bt_config = BacktestConfig(symbol="EUR/USD", timeframe="d1")
    candidates = {"only": make_fake_runner(4, profit_factor=1.5, config=bt_config)}
    report = run_walk_forward(candles, windows, candidates, bt_config)
    assert report.aggregate.total_oos_trades == len(report.window_results) * 4


def test_aggregate_report_has_required_fields():
    config = WalkForwardConfig(development_days=10, validation_days=5, out_of_sample_days=5, step_days=5)
    candles = make_candles(20)
    windows = generate_walk_forward_windows(candles, config)
    bt_config = BacktestConfig(symbol="EUR/USD", timeframe="d1")
    candidates = {"only": make_fake_runner(5, profit_factor=1.5, config=bt_config)}
    report = run_walk_forward(candles, windows, candidates, bt_config)
    agg = report.aggregate
    assert hasattr(agg, "total_oos_trades")
    assert hasattr(agg, "windows_with_selection")
    assert hasattr(agg, "windows_without_selection")
    assert hasattr(agg, "combined_oos_win_rate")
    assert hasattr(agg, "combined_oos_profit_factor")


def test_window_result_contains_required_audit_fields():
    config = WalkForwardConfig(development_days=10, validation_days=5, out_of_sample_days=5, step_days=5)
    candles = make_candles(20)
    windows = generate_walk_forward_windows(candles, config)
    bt_config = BacktestConfig(symbol="EUR/USD", timeframe="d1")
    candidates = {"only": make_fake_runner(3, profit_factor=1.4, config=bt_config)}
    report = run_walk_forward(candles, windows, candidates, bt_config)
    w = report.window_results[0]
    assert w.periods is not None
    assert w.selected_candidate is not None
    assert w.oos_result is not None
    assert w.oos_result.summary.trade_count == 3
    assert w.oos_result.summary.profit_factor == 1.4


def test_report_never_claims_profitability_in_its_own_structure():
    import dataclasses
    from app.research.walk_forward import WalkForwardAggregate
    field_names = {f.name for f in dataclasses.fields(WalkForwardAggregate)}
    for forbidden in ("is_profitable", "proven", "guaranteed", "will_profit"):
        assert forbidden not in field_names
