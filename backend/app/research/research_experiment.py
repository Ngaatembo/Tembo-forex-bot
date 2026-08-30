"""
ResearchExperiment: the full record of one hypothesis tested against
one dataset, across development/validation/out-of-sample periods, with
baseline comparison, overfitting diagnostics, and a deterministic
verdict. Saved append-only (same pattern as Phase 6's experiment.py)
— never overwritten, so no experiment result is ever silently lost or
replaced by a later run.
"""

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from app.backtesting.config import BacktestConfig
from app.backtesting.engine_research import simulate_trades_with_exit_rules
from app.backtesting.exit_rules import BASELINE_EXIT
from app.backtesting.models import BacktestSummary
from app.data_engine.market_data import Candle
from app.research.baseline import compute_baseline_summary
from app.research.baseline_comparison import PeriodComparison, compare_to_baseline
from app.research.dataset_version import DatasetVersion
from app.research.hypothesis import Hypothesis
from app.research.overfitting import OverfittingDiagnostics, compute_overfitting_diagnostics
from app.research.periods import EvaluationPeriods, split_candles_by_period
from app.research.rule_signal_generator import generate_signals_from_hypothesis
from app.research.verdict import Verdict, compute_verdict
from app.technical_engine.features import calculate_feature_snapshots

STRATEGY_VERSION_TEMPLATE = "hypothesis_{id}_v{version}"


@dataclass
class ResearchExperiment:
    experiment_id: str
    hypothesis_id: str
    hypothesis_version: int
    strategy_version: str
    dataset: DatasetVersion
    symbol: str
    timeframe: str
    periods: EvaluationPeriods
    transaction_cost_model: dict
    slippage_model: dict
    risk_configuration: dict
    metrics: dict  # {"development": {...}, "validation": {...}, "out_of_sample": {...}}
    baseline_comparison: dict  # {"development": PeriodComparison.to_dict(), ...}
    overfitting_diagnostics: dict
    verdict: str
    created_at: str
    reproducibility_metadata: dict

    def to_dict(self) -> dict:
        d = asdict(self)
        d["dataset"] = self.dataset.to_dict()
        d["periods"] = self.periods.to_dict()
        return d


def _summary_to_dict(s: BacktestSummary) -> dict:
    return asdict(s)


def run_research_experiment(
    hypothesis: Hypothesis,
    all_candles: list[Candle],
    dataset: DatasetVersion,
    periods: EvaluationPeriods,
    cost_config: dict,  # {"spread": float, "slippage": float}
    account_config: dict,  # {"initial_balance": float, "position_size": float}
) -> ResearchExperiment:
    split = split_candles_by_period(all_candles, periods)

    period_summaries: dict[str, BacktestSummary] = {}
    baseline_summaries: dict[str, BacktestSummary] = {}

    for label, candles in split.items():
        config = BacktestConfig(**account_config, **cost_config)

        if not candles:
            # No candles in this slice — an empty-but-valid summary,
            # never a crash. compute via the frozen baseline helper's
            # own empty-safe engine (simulate_trades handles empty input).
            baseline_summaries[label] = compute_baseline_summary([], config)
            period_summaries[label] = compute_baseline_summary([], config)  # both empty -> both trivial
            continue

        features = calculate_feature_snapshots(candles)
        signals = generate_signals_from_hypothesis(hypothesis, candles, features)
        result = simulate_trades_with_exit_rules(candles, signals, features, config, BASELINE_EXIT)
        period_summaries[label] = result.summary

        baseline_summaries[label] = compute_baseline_summary(candles, config)

    baseline_comparison = {
        label: compare_to_baseline(label, baseline_summaries[label], period_summaries[label]).to_dict()
        for label in ("development", "validation", "out_of_sample")
    }

    overfitting = compute_overfitting_diagnostics(
        period_summaries["development"], period_summaries["validation"], period_summaries["out_of_sample"]
    )

    verdict = compute_verdict(
        period_summaries["development"], period_summaries["validation"], period_summaries["out_of_sample"]
    )

    return ResearchExperiment(
        experiment_id=f"exp_{uuid.uuid4().hex[:10]}",
        hypothesis_id=hypothesis.id, hypothesis_version=hypothesis.version,
        strategy_version=STRATEGY_VERSION_TEMPLATE.format(id=hypothesis.id, version=hypothesis.version),
        dataset=dataset, symbol=hypothesis.market, timeframe=hypothesis.timeframe, periods=periods,
        transaction_cost_model={"spread": cost_config.get("spread"), "cost_note": "half-spread each side, see portfolio.py"},
        slippage_model={"slippage": cost_config.get("slippage")},
        risk_configuration=account_config,
        metrics={label: _summary_to_dict(s) for label, s in period_summaries.items()},
        baseline_comparison=baseline_comparison,
        overfitting_diagnostics=asdict(overfitting),
        verdict=verdict.value,
        created_at=datetime.now(timezone.utc).isoformat(),
        reproducibility_metadata={
            "dataset_sha256": dataset.sha256, "dataset_id": dataset.dataset_id,
            "candle_count": len(all_candles),
        },
    )


def save_research_experiment(experiment: ResearchExperiment, registry_path: str) -> None:
    """Append-only — same discipline as the hypothesis registry."""
    path = Path(registry_path)
    records = json.loads(path.read_text()) if path.exists() else []
    records.append(experiment.to_dict())
    path.write_text(json.dumps(records, indent=2, default=str))


def load_research_experiments(registry_path: str) -> list[dict]:
    path = Path(registry_path)
    if not path.exists():
        return []
    return json.loads(path.read_text())
