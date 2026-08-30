import json
from datetime import datetime, timezone

from app.backtesting.models import BacktestSummary
from app.research.experiment import (
    BASELINE_STRATEGY_VERSION, build_experiment_record, load_experiments,
    make_experiment_id, save_experiment,
)


def dummy_summary() -> BacktestSummary:
    return BacktestSummary(
        initial_balance=1000.0, final_balance=1100.0, net_pnl=100.0,
        total_return=0.1, trade_count=5, win_rate=0.6,
    )


def test_experiment_ids_are_unique():
    ids = {make_experiment_id("test") for _ in range(20)}
    assert len(ids) == 20


def test_experiment_id_includes_prefix():
    exp_id = make_experiment_id("fixed_stop")
    assert exp_id.startswith("fixed_stop_")


def test_build_experiment_record_captures_full_reproducibility_context():
    record = build_experiment_record(
        experiment_id="exp_1", strategy_version=BASELINE_STRATEGY_VERSION,
        entry_rule_label="baseline", exit_rule_label="baseline",
        risk_config_label="fixed_10000", dataset_id="ejtrader_eurusd_h1",
        period_label="train_dev",
        period_start=datetime(2012, 11, 16, tzinfo=timezone.utc),
        period_end=datetime(2019, 5, 24, tzinfo=timezone.utc),
        candle_count=40320, spread=0.0001, slippage=0.00002,
        initial_balance=10000.0, position_size=10000.0, summary=dummy_summary(),
    )
    assert record.strategy_version == BASELINE_STRATEGY_VERSION
    assert record.candle_count == 40320
    assert record.summary["trade_count"] == 5


def test_save_and_load_roundtrip(tmp_path):
    registry_path = tmp_path / "experiments.json"
    record = build_experiment_record(
        experiment_id="exp_1", strategy_version=BASELINE_STRATEGY_VERSION,
        entry_rule_label="baseline", exit_rule_label="baseline",
        risk_config_label="fixed_10000", dataset_id="test_dataset",
        period_label="full_period",
        period_start=datetime(2020, 1, 1, tzinfo=timezone.utc),
        period_end=datetime(2020, 1, 2, tzinfo=timezone.utc),
        candle_count=24, spread=0.0001, slippage=0.0,
        initial_balance=1000.0, position_size=1000.0, summary=dummy_summary(),
    )
    save_experiment(record, registry_path)

    loaded = load_experiments(registry_path)
    assert len(loaded) == 1
    assert loaded[0]["experiment_id"] == "exp_1"


def test_save_experiment_is_append_only_never_overwrites(tmp_path):
    registry_path = tmp_path / "experiments.json"

    for i in range(3):
        record = build_experiment_record(
            experiment_id=f"exp_{i}", strategy_version=BASELINE_STRATEGY_VERSION,
            entry_rule_label="baseline", exit_rule_label="baseline",
            risk_config_label="fixed_10000", dataset_id="test_dataset",
            period_label="full_period",
            period_start=datetime(2020, 1, 1, tzinfo=timezone.utc),
            period_end=datetime(2020, 1, 2, tzinfo=timezone.utc),
            candle_count=24, spread=0.0001, slippage=0.0,
            initial_balance=1000.0, position_size=1000.0, summary=dummy_summary(),
        )
        save_experiment(record, registry_path)

    loaded = load_experiments(registry_path)
    assert len(loaded) == 3
    assert [r["experiment_id"] for r in loaded] == ["exp_0", "exp_1", "exp_2"]


def test_load_experiments_missing_file_returns_empty_list(tmp_path):
    assert load_experiments(tmp_path / "does_not_exist.json") == []


def test_experiment_record_is_json_serializable(tmp_path):
    record = build_experiment_record(
        experiment_id="exp_1", strategy_version=BASELINE_STRATEGY_VERSION,
        entry_rule_label="avoid_low_volatility", exit_rule_label="fixed_stop_1pct",
        risk_config_label="fixed_10000", dataset_id="test_dataset",
        period_label="validation",
        period_start=datetime(2019, 5, 24, tzinfo=timezone.utc),
        period_end=datetime(2020, 10, 14, tzinfo=timezone.utc),
        candle_count=8640, spread=0.0001, slippage=0.00002,
        initial_balance=10000.0, position_size=10000.0, summary=dummy_summary(),
    )
    registry_path = tmp_path / "experiments.json"
    save_experiment(record, registry_path)
    # If this parses without error, it's valid JSON — the roundtrip is the assertion.
    json.loads(registry_path.read_text())
