"""
ValidatedStrategyConfig — bridges "which researched candidate" (Phase
10's StrategyCandidate, referenced by ID, never copied) with "for
which specific instrument/timeframe/parameter configuration." A
single strategy family (e.g. breakout) can have several
ValidatedStrategyConfigs — one per instrument/timeframe/lookback
combination actually tested — since Phase 10's StrategyCandidate is
deliberately more abstract (it doesn't carry instrument/timeframe at
all).

WHY THIS CANNOT BY ITSELF AUTHORIZE TRADING: gate_status, verdict, and
statistical_level here are a SNAPSHOT of evidence at creation time —
read-only, immutable, informational. Nothing in this dataclass has an
execute() method, a callable, or any path to the execution/broker layer. Whether a
config is actually tradeable is a judgment the separate
strategy_selector.py makes by READING this snapshot, never something
this object claims about itself. A gate_status of "PAPER_CANDIDATE"
recorded here still means exactly what Phase 10 always said it means:
a human MAY consider a separate paper-trading decision — never
automatic authorization.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Optional

from app.research.hypothesis import HypothesisType

KNOWN_GATE_STATUSES = frozenset({
    "REJECT_EARLY", "RESEARCH", "ROBUSTNESS_REQUIRED", "PROMISING", "PAPER_CANDIDATE", "CLOSED",
})
KNOWN_STATISTICAL_LEVELS = frozenset({"STRONG", "MODERATE", "WEAK", "UNKNOWN"})


@dataclass(frozen=True)
class ValidatedStrategyConfig:
    config_id: str
    candidate_id: str
    instrument: str
    timeframe: str
    strategy_family: HypothesisType
    parameters: dict
    exit_config_summary: dict
    cost_assumptions: dict
    evidence_period_start: str
    evidence_period_end: str

    gate_status: str
    verdict: str
    statistical_level: str
    regime_evidence: dict

    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def __post_init__(self):
        if self.gate_status not in KNOWN_GATE_STATUSES:
            raise ValueError(f"Unknown gate_status {self.gate_status!r}. Allowed: {sorted(KNOWN_GATE_STATUSES)}")
        if self.statistical_level not in KNOWN_STATISTICAL_LEVELS:
            raise ValueError(f"Unknown statistical_level {self.statistical_level!r}.")
        if not self.instrument or not self.timeframe:
            raise ValueError("instrument and timeframe are both required — a config must be specific.")

    def to_dict(self) -> dict:
        d = asdict(self)
        d["strategy_family"] = self.strategy_family.value
        return d

    @staticmethod
    def from_dict(d: dict) -> "ValidatedStrategyConfig":
        return ValidatedStrategyConfig(
            config_id=d["config_id"], candidate_id=d["candidate_id"],
            instrument=d["instrument"], timeframe=d["timeframe"],
            strategy_family=HypothesisType(d["strategy_family"]),
            parameters=d["parameters"], exit_config_summary=d["exit_config_summary"],
            cost_assumptions=d["cost_assumptions"],
            evidence_period_start=d["evidence_period_start"], evidence_period_end=d["evidence_period_end"],
            gate_status=d["gate_status"], verdict=d["verdict"],
            statistical_level=d["statistical_level"], regime_evidence=d["regime_evidence"],
            created_at=d["created_at"],
        )


def new_config_id(instrument: str, timeframe: str, family: str) -> str:
    import uuid
    slug = f"{instrument}_{timeframe}_{family}".lower().replace("/", "").replace(" ", "_")
    return f"vsc_{slug}_{uuid.uuid4().hex[:8]}"
