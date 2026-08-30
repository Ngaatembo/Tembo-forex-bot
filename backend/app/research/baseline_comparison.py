"""
Compares a candidate experiment's results against the frozen baseline,
period by period. Reports the numbers side by side — deliberately does
NOT compute a single "winner" flag. A candidate with a higher return
but a much higher drawdown, or on a much smaller trade count, is not
straightforwardly "better," and this module refuses to pretend it is.
"""

from dataclasses import asdict, dataclass

from app.backtesting.models import BacktestSummary


@dataclass
class PeriodComparison:
    period_label: str
    baseline_trade_count: int
    candidate_trade_count: int
    baseline_return: float
    candidate_return: float
    baseline_profit_factor: float | None
    candidate_profit_factor: float | None
    baseline_max_drawdown_percent: float | None
    candidate_max_drawdown_percent: float | None
    baseline_win_rate: float | None
    candidate_win_rate: float | None

    def to_dict(self) -> dict:
        return asdict(self)


def compare_to_baseline(
    period_label: str, baseline: BacktestSummary, candidate: BacktestSummary
) -> PeriodComparison:
    return PeriodComparison(
        period_label=period_label,
        baseline_trade_count=baseline.trade_count, candidate_trade_count=candidate.trade_count,
        baseline_return=baseline.total_return, candidate_return=candidate.total_return,
        baseline_profit_factor=baseline.profit_factor, candidate_profit_factor=candidate.profit_factor,
        baseline_max_drawdown_percent=baseline.max_drawdown_percent,
        candidate_max_drawdown_percent=candidate.max_drawdown_percent,
        baseline_win_rate=baseline.win_rate, candidate_win_rate=candidate.win_rate,
    )
