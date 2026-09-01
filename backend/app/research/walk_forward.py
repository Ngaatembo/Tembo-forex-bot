"""
Rolling walk-forward validation orchestrator.

Reuses app/research/periods.py's EvaluationPeriods (chronological
enforcement, unmodified) for each window's internal dev/validation/OOS
split, and is completely agnostic to which backtesting engine actually
runs a candidate -- callers supply a `run_window(candles, config) ->
BacktestResult` callable per candidate, wrapping either
app.backtesting.engine.simulate_trades or
app.backtesting.engine_research.simulate_trades_with_exit_rules (or
any strategy_engine signal generator) themselves. This module contains
NO strategy logic and NO second backtesting engine -- only window
generation, dev/validation-only selection, and OOS-only aggregation.

METHODOLOGICAL NOTE, stated once here rather than repeated everywhere:
walk-forward validation is a STRONGER TEST of whether a strategy's
historical performance survives repeated unseen out-of-sample periods.
It is NOT proof of future profitability, and nothing in this module
computes, exposes, or implies such a claim -- see
WalkForwardAggregate's fields and
test_report_never_claims_profitability_in_its_own_structure.
"""

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Callable, Optional

from app.backtesting.config import BacktestConfig
from app.backtesting.models import BacktestResult
from app.research.periods import EvaluationPeriod, EvaluationPeriods, split_candles_by_period

RunWindowFn = Callable[[list, BacktestConfig], BacktestResult]


class InsufficientDataError(Exception):
    """Raised when the provided candles cannot fit even one full
    development+validation+out_of_sample window. Never silently
    produces zero windows or a misleadingly empty report."""


@dataclass(frozen=True)
class WalkForwardConfig:
    development_days: int
    validation_days: int
    out_of_sample_days: int
    step_days: int

    def __post_init__(self):
        for name, value in (
            ("development_days", self.development_days), ("validation_days", self.validation_days),
            ("out_of_sample_days", self.out_of_sample_days), ("step_days", self.step_days),
        ):
            if value <= 0:
                raise ValueError(f"{name} must be positive, got {value}.")

    @property
    def window_span_days(self) -> int:
        return self.development_days + self.validation_days + self.out_of_sample_days


@dataclass(frozen=True)
class WalkForwardWindow:
    index: int
    periods: EvaluationPeriods


def generate_walk_forward_windows(candles: list, config: WalkForwardConfig) -> list[WalkForwardWindow]:
    if not candles:
        raise InsufficientDataError("No candles provided.")

    data_start = candles[0].timestamp
    data_end = candles[-1].timestamp
    span = timedelta(days=config.window_span_days)
    # Periods are exclusive-end (see periods.py) -- the last candle
    # actually usable in a window is at (window_start + span - 1 day),
    # so the required data span is (span - 1 day), not span.
    required_span = span - timedelta(days=1)

    if data_end - data_start < required_span:
        raise InsufficientDataError(
            f"Data covers {data_start} to {data_end} ({(data_end - data_start).days} days), "
            f"but one window needs at least {required_span.days} days of coverage "
            f"(development={config.development_days} + validation={config.validation_days} "
            f"+ out_of_sample={config.out_of_sample_days})."
        )

    windows = []
    dev_start = data_start
    index = 0
    while True:
        val_start = dev_start + timedelta(days=config.development_days)
        oos_start = val_start + timedelta(days=config.validation_days)
        oos_end = oos_start + timedelta(days=config.out_of_sample_days)
        if oos_end - timedelta(days=1) > data_end:
            break

        periods = EvaluationPeriods(
            development=EvaluationPeriod("development", dev_start, val_start),
            validation=EvaluationPeriod("validation", val_start, oos_start),
            out_of_sample=EvaluationPeriod("out_of_sample", oos_start, oos_end),
        )
        windows.append(WalkForwardWindow(index=index, periods=periods))
        index += 1
        dev_start = dev_start + timedelta(days=config.step_days)

    if not windows:
        raise InsufficientDataError(
            f"Data does not fit any complete window (span={config.window_span_days} days)."
        )
    return windows


@dataclass(frozen=True)
class WalkForwardWindowResult:
    index: int
    periods: EvaluationPeriods
    candidate_scores: dict
    selected_candidate: Optional[str]
    oos_result: Optional[BacktestResult]


@dataclass(frozen=True)
class WalkForwardAggregate:
    windows_total: int
    windows_with_selection: int
    windows_without_selection: int
    total_oos_trades: int
    combined_oos_win_rate: Optional[float]
    combined_oos_profit_factor: Optional[float]
    combined_oos_expectancy: Optional[float]
    worst_oos_max_drawdown: Optional[float]


@dataclass(frozen=True)
class WalkForwardReport:
    config: Optional[WalkForwardConfig]
    window_results: list = field(default_factory=list)
    aggregate: Optional[WalkForwardAggregate] = None


def _select_candidate(candidates: dict, dev_val_candles: list, backtest_config: BacktestConfig):
    scores = {}
    best_label = None
    best_score = None
    for label, run_window in candidates.items():
        result = run_window(dev_val_candles, backtest_config)
        trade_count = result.summary.trade_count
        pf = result.summary.profit_factor
        scores[label] = pf if trade_count > 0 else None
        if trade_count == 0 or pf is None:
            continue
        if best_score is None or pf > best_score:
            best_score = pf
            best_label = label
    return best_label, scores


def run_walk_forward(
    candles: list, windows: list, candidates: dict, backtest_config: BacktestConfig,
) -> WalkForwardReport:
    window_results = []
    for window in windows:
        split = split_candles_by_period(candles, window.periods)
        dev_val_candles = split["development"] + split["validation"]

        selected_label, scores = _select_candidate(candidates, dev_val_candles, backtest_config)

        oos_result = None
        if selected_label is not None:
            oos_candles = split["out_of_sample"]
            oos_result = candidates[selected_label](oos_candles, backtest_config)

        window_results.append(WalkForwardWindowResult(
            index=window.index, periods=window.periods, candidate_scores=scores,
            selected_candidate=selected_label, oos_result=oos_result,
        ))

    aggregate = _aggregate_oos_results(window_results)
    return WalkForwardReport(config=None, window_results=window_results, aggregate=aggregate)


def _aggregate_oos_results(window_results: list) -> WalkForwardAggregate:
    oos_summaries = [w.oos_result.summary for w in window_results if w.oos_result is not None]
    windows_with_selection = len(oos_summaries)
    windows_without_selection = len(window_results) - windows_with_selection

    total_trades = sum(s.trade_count for s in oos_summaries)

    total_wins = sum(s.winning_trades or 0 for s in oos_summaries)
    combined_win_rate = (total_wins / total_trades) if total_trades > 0 else None

    pf_values = [(s.profit_factor, s.trade_count) for s in oos_summaries if s.profit_factor is not None and s.trade_count > 0]
    combined_pf = (
        sum(pf * n for pf, n in pf_values) / sum(n for _, n in pf_values) if pf_values else None
    )
    exp_values = [(s.expectancy, s.trade_count) for s in oos_summaries if s.expectancy is not None and s.trade_count > 0]
    combined_expectancy = (
        sum(e * n for e, n in exp_values) / sum(n for _, n in exp_values) if exp_values else None
    )

    dd_values = [s.max_drawdown for s in oos_summaries if s.max_drawdown is not None]
    worst_dd = max(dd_values) if dd_values else None

    return WalkForwardAggregate(
        windows_total=len(window_results), windows_with_selection=windows_with_selection,
        windows_without_selection=windows_without_selection, total_oos_trades=total_trades,
        combined_oos_win_rate=combined_win_rate, combined_oos_profit_factor=combined_pf,
        combined_oos_expectancy=combined_expectancy, worst_oos_max_drawdown=worst_dd,
    )
