from datetime import datetime, timezone

from app.research.dataset_version import DatasetVersion
from app.research.hypothesis import Condition, Hypothesis, HypothesisType, RuleSet
from app.research.periods import EvaluationPeriod, EvaluationPeriods
from app.research.research_experiment import (
    load_research_experiments, run_research_experiment, save_research_experiment,
)
from app.research.verdict import Verdict
from tests.fixtures.backtest_fixtures import trending_candles


def make_momentum_hypothesis() -> Hypothesis:
    return Hypothesis(
        id="test_momentum", name="Test Momentum", description="d", hypothesis_type=HypothesisType.MOMENTUM,
        market="EUR/USD", timeframe="1h",
        entry_long=RuleSet(conditions=(Condition(field="rsi_14", operator=">", value=55.0),)),
        entry_short=RuleSet(conditions=(Condition(field="rsi_14", operator="<", value=45.0),)),
        risk_conditions={}, rationale="r", data_requirements=("rsi_14",),
    )


def make_periods(candles) -> EvaluationPeriods:
    n = len(candles)
    return EvaluationPeriods(
        development=EvaluationPeriod("development", candles[0].timestamp, candles[n // 2].timestamp),
        validation=EvaluationPeriod("validation", candles[n // 2].timestamp, candles[3 * n // 4].timestamp),
        out_of_sample=EvaluationPeriod("out_of_sample", candles[3 * n // 4].timestamp, candles[-1].timestamp + __import__("datetime").timedelta(hours=1)),
    )


def make_dataset() -> DatasetVersion:
    return DatasetVersion(
        dataset_id="TEST_SYNTHETIC_v1", source="synthetic test fixture", license="n/a",
        symbol="EUR/USD", timeframe="1h", period_start="2024-01-08", period_end="2024-01-14",
        candle_count=140, import_version="v1", sha256=None,
    )


def test_full_experiment_pipeline_runs_end_to_end():
    candles = trending_candles()  # 140 synthetic candles, real crossovers present (Phase 4 fixture)
    hypothesis = make_momentum_hypothesis()
    periods = make_periods(candles)
    dataset = make_dataset()

    experiment = run_research_experiment(
        hypothesis, candles, dataset, periods,
        cost_config={"spread": 0.0001, "slippage": 0.0},
        account_config={"initial_balance": 10000.0, "position_size": 10000.0},
    )

    assert experiment.hypothesis_id == "test_momentum"
    assert experiment.verdict in [v.value for v in Verdict]
    assert set(experiment.metrics.keys()) == {"development", "validation", "out_of_sample"}
    assert set(experiment.baseline_comparison.keys()) == {"development", "validation", "out_of_sample"}


def test_experiment_is_reproducible():
    candles = trending_candles()
    hypothesis = make_momentum_hypothesis()
    periods = make_periods(candles)
    dataset = make_dataset()
    cost_config = {"spread": 0.0001, "slippage": 0.0}
    account_config = {"initial_balance": 10000.0, "position_size": 10000.0}

    exp1 = run_research_experiment(hypothesis, candles, dataset, periods, cost_config, account_config)
    exp2 = run_research_experiment(hypothesis, candles, dataset, periods, cost_config, account_config)

    assert exp1.metrics == exp2.metrics
    assert exp1.verdict == exp2.verdict


def test_experiment_save_and_load_is_append_only(tmp_path):
    registry = str(tmp_path / "experiments.json")
    candles = trending_candles()
    hypothesis = make_momentum_hypothesis()
    periods = make_periods(candles)
    dataset = make_dataset()

    exp1 = run_research_experiment(
        hypothesis, candles, dataset, periods,
        {"spread": 0.0001, "slippage": 0.0}, {"initial_balance": 10000.0, "position_size": 10000.0},
    )
    save_research_experiment(exp1, registry)
    exp2 = run_research_experiment(
        hypothesis, candles, dataset, periods,
        {"spread": 0.0002, "slippage": 0.0}, {"initial_balance": 10000.0, "position_size": 10000.0},
    )
    save_research_experiment(exp2, registry)

    records = load_research_experiments(registry)
    assert len(records) == 2  # both preserved, nothing overwritten
    assert records[0]["experiment_id"] != records[1]["experiment_id"]
