"""
Reproducible experiment framework for Phase 6.

Every experiment run produces an ExperimentRecord capturing exactly
what produced its results — strategy version, entry/exit rule labels,
cost assumptions, dataset period — so results are never separated from
the configuration that generated them.

APPEND-ONLY: `save_experiment()` always appends to the registry file,
never overwrites a previous entry. Re-running the "same" experiment
produces a new record with a new experiment_id, not a silent
replacement — the point of this module is to never lose track of
which rule produced which result.
"""

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from app.backtesting.models import BacktestSummary

BASELINE_STRATEGY_VERSION = "baseline_sma_10_50_v1"


@dataclass
class ExperimentRecord:
    experiment_id: str
    strategy_version: str
    entry_rule_label: str
    exit_rule_label: str
    risk_config_label: str
    dataset_id: str
    period_label: str  # e.g. "train_dev", "validation", "out_of_sample", "full_period"
    period_start: str
    period_end: str
    candle_count: int
    spread: float
    slippage: float
    initial_balance: float
    position_size: float
    summary: dict
    created_at: str


def make_experiment_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def build_experiment_record(
    *, experiment_id: str, strategy_version: str, entry_rule_label: str, exit_rule_label: str,
    risk_config_label: str, dataset_id: str, period_label: str,
    period_start: datetime, period_end: datetime, candle_count: int,
    spread: float, slippage: float, initial_balance: float, position_size: float,
    summary: BacktestSummary,
) -> ExperimentRecord:
    return ExperimentRecord(
        experiment_id=experiment_id, strategy_version=strategy_version,
        entry_rule_label=entry_rule_label, exit_rule_label=exit_rule_label,
        risk_config_label=risk_config_label, dataset_id=dataset_id, period_label=period_label,
        period_start=period_start.isoformat(), period_end=period_end.isoformat(),
        candle_count=candle_count, spread=spread, slippage=slippage,
        initial_balance=initial_balance, position_size=position_size,
        summary=asdict(summary), created_at=datetime.now(timezone.utc).isoformat(),
    )


def save_experiment(record: ExperimentRecord, registry_path: Path) -> None:
    """Appends one JSON line to the registry file. Never truncates or
    rewrites existing entries — creates the file (with an empty list
    serialized as the starting point) only if it doesn't exist yet."""
    registry_path.parent.mkdir(parents=True, exist_ok=True)

    existing: list[dict] = []
    if registry_path.exists():
        existing = json.loads(registry_path.read_text())

    existing.append(asdict(record))
    registry_path.write_text(json.dumps(existing, indent=2))


def load_experiments(registry_path: Path) -> list[dict]:
    if not registry_path.exists():
        return []
    return json.loads(registry_path.read_text())
