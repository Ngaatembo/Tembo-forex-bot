"""
StrategyCandidate — a thin, evidence-referencing wrapper, NOT a new
experiment model and NOT executable strategy code.

WHAT THIS IS: a way to say "these ResearchExperiment records (Phase
7's existing model, referenced here only by ID string, never copied)
all belong to the same research investigation." H1's Phase 8
experiment and its Phase 8.1 robustness follow-up are two separate,
already-existing experiment records; a StrategyCandidate is the label
that connects them as one line of inquiry, without duplicating or
modifying either.

WHY IT'S FROZEN (immutable) AND REFERENCE-ONLY: the project's standing
rule is "never overwrite research history." A candidate that could be
edited in place, or that embedded live/mutable/executable data, would
be a way around that rule. This dataclass holds only JSON-safe
strings, an enum, and a tuple of ID references — there is no field
anywhere that can hold code, a callable, or a database connection.

`family` reuses `HypothesisType` directly (Phase 7) — deliberately not
a second, competing taxonomy.
"""

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.research.hypothesis import HypothesisType


@dataclass(frozen=True)
class StrategyCandidate:
    candidate_id: str
    name: str
    family: HypothesisType
    description: str
    experiment_ids: tuple[str, ...]
    parent_candidate_id: Optional[str]
    lineage_note: Optional[str]
    research_priority: Optional[str]   # set by a later chunk (research_priority.py) — None until then
    gate_status: Optional[str]          # set by a later chunk (research_gate.py) — None until then
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    verdict: Optional[str] = None       # the underlying Verdict.value (Chunk 5 addition — see module docstring)

    def __post_init__(self):
        if not isinstance(self.family, HypothesisType):
            raise ValueError(
                f"family must be a HypothesisType, got {self.family!r}. "
                f"Allowed: {[t.value for t in HypothesisType]}"
            )
        if not self.experiment_ids:
            raise ValueError(
                "A StrategyCandidate must reference at least one experiment_id — "
                "it represents accumulated evidence, not evidence-free speculation."
            )
        if not all(isinstance(e, str) for e in self.experiment_ids):
            raise ValueError("Every experiment_id must be a string.")

    def to_dict(self) -> dict:
        d = asdict(self)
        d["family"] = self.family.value
        d["experiment_ids"] = list(self.experiment_ids)
        return d

    @staticmethod
    def from_dict(d: dict) -> "StrategyCandidate":
        return StrategyCandidate(
            candidate_id=d["candidate_id"], name=d["name"],
            family=HypothesisType(d["family"]), description=d["description"],
            experiment_ids=tuple(d["experiment_ids"]),
            parent_candidate_id=d.get("parent_candidate_id"),
            lineage_note=d.get("lineage_note"),
            research_priority=d.get("research_priority"),
            gate_status=d.get("gate_status"),
            created_at=d["created_at"],
            verdict=d.get("verdict"),
        )


def new_candidate_id(name: str) -> str:
    slug = "".join(c.lower() if c.isalnum() else "_" for c in name).strip("_")
    return f"cand_{slug}_{uuid.uuid4().hex[:8]}"


def validate_experiment_ids_exist(candidate: StrategyCandidate, known_experiment_ids: set) -> list[str]:
    """
    Returns the list of experiment_ids the candidate references that
    are NOT found in `known_experiment_ids` — empty list if all exist.
    Deliberately a separate function, not part of __post_init__: the
    candidate dataclass itself does no file I/O and has no dependency
    on where experiment records live, keeping it a pure data object.
    """
    return [eid for eid in candidate.experiment_ids if eid not in known_experiment_ids]


def save_candidate(candidate: StrategyCandidate, registry_path: str) -> None:
    """Append-only — same discipline as hypothesis_registry.py and
    research_experiment.py's save functions. Never overwrites a prior entry."""
    path = Path(registry_path)
    records = json.loads(path.read_text()) if path.exists() else []
    records.append(candidate.to_dict())
    path.write_text(json.dumps(records, indent=2))


def load_candidates(registry_path: str) -> list[StrategyCandidate]:
    path = Path(registry_path)
    if not path.exists():
        return []
    records = json.loads(path.read_text())
    return [StrategyCandidate.from_dict(r) for r in records]
