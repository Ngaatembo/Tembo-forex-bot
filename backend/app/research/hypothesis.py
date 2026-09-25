"""
Structured research hypothesis model.

SECURITY-CRITICAL DESIGN PRINCIPLE: a Hypothesis can only ever contain
JSON-safe data — strings, numbers, and Condition objects built from a
closed, validated set of feature names and comparison operators. There
is no field anywhere in this model that can hold a Python expression,
a callable, a SQL string, or any other executable payload.

Book/source provenance is metadata only. It records which source claims
informed a hypothesis and how they were operationalized; it never
changes evaluation semantics or executes source text.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum

ALLOWED_CONDITION_FIELDS = frozenset({
    "close", "sma_10", "sma_50", "sma_50_slope", "sma_distance", "sma_distance_pct",
    "rsi_14", "atr_14", "atr_percent",
    "recent_high", "recent_low", "rolling_range", "distance_from_high", "distance_from_low",
})

ALLOWED_OPERATORS = frozenset({">", "<", ">=", "<=", "==", "!="})


class HypothesisType(str, Enum):
    TREND_FOLLOWING = "trend_following"
    MEAN_REVERSION = "mean_reversion"
    BREAKOUT = "breakout"
    MOMENTUM = "momentum"
    VOLATILITY = "volatility"
    MARKET_REGIME = "market_regime"
    EVENT_DRIVEN = "event_driven"
    NEWS_DRIVEN = "news_driven"
    STATISTICAL = "statistical"
    CORRELATION = "correlation"
    HYBRID = "hybrid"


class HypothesisStatus(str, Enum):
    DRAFT = "draft"
    REGISTERED = "registered"
    TESTED = "tested"
    ARCHIVED = "archived"


@dataclass(frozen=True)
class Condition:
    """One deterministic comparison: field OP value, or field OP compare_field."""
    field: str
    operator: str
    value: float | None = None
    compare_field: str | None = None

    def __post_init__(self):
        if self.field not in ALLOWED_CONDITION_FIELDS:
            raise ValueError(
                f"Unknown condition field {self.field!r}. Allowed: {sorted(ALLOWED_CONDITION_FIELDS)}"
            )
        if self.operator not in ALLOWED_OPERATORS:
            raise ValueError(f"Unknown operator {self.operator!r}. Allowed: {sorted(ALLOWED_OPERATORS)}")
        if (self.value is None) == (self.compare_field is None):
            raise ValueError("Exactly one of value or compare_field must be set.")
        if self.compare_field is not None and self.compare_field not in ALLOWED_CONDITION_FIELDS:
            raise ValueError(f"Unknown compare_field {self.compare_field!r}.")
        if self.value is not None and not isinstance(self.value, (int, float)):
            raise ValueError(f"Condition.value must be numeric, got {type(self.value)}.")

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Condition":
        return Condition(
            field=d["field"], operator=d["operator"],
            value=d.get("value"), compare_field=d.get("compare_field"),
        )


@dataclass(frozen=True)
class RuleSet:
    """A list of Conditions, ANDed together. Empty means 'always true'."""
    conditions: tuple[Condition, ...] = ()

    def to_dict(self) -> dict:
        return {"conditions": [c.to_dict() for c in self.conditions]}

    @staticmethod
    def from_dict(d: dict) -> "RuleSet":
        return RuleSet(conditions=tuple(Condition.from_dict(c) for c in d.get("conditions", [])))


@dataclass(frozen=True)
class HypothesisProvenance:
    """
    Non-executable provenance linking a hypothesis to source material.

    source_id and claim_id refer to records in the project's source/claim
    registries. mapping_note describes Tembo's operationalization; it is
    documentation, not an evaluator instruction.
    """
    source_id: str
    claim_id: str
    mapping_note: str

    def __post_init__(self):
        if not self.source_id.strip():
            raise ValueError("source_id must not be empty.")
        if not self.claim_id.strip():
            raise ValueError("claim_id must not be empty.")
        if not self.mapping_note.strip():
            raise ValueError("mapping_note must not be empty.")

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "HypothesisProvenance":
        return HypothesisProvenance(
            source_id=d["source_id"],
            claim_id=d["claim_id"],
            mapping_note=d["mapping_note"],
        )


@dataclass(frozen=True)
class Hypothesis:
    id: str
    name: str
    description: str
    hypothesis_type: HypothesisType
    market: str
    timeframe: str
    entry_long: RuleSet
    entry_short: RuleSet
    risk_conditions: dict
    rationale: str
    data_requirements: tuple[str, ...]
    status: HypothesisStatus = HypothesisStatus.DRAFT
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    version: int = 1
    provenance: tuple[HypothesisProvenance, ...] = ()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["hypothesis_type"] = self.hypothesis_type.value
        d["status"] = self.status.value
        d["entry_long"] = self.entry_long.to_dict()
        d["entry_short"] = self.entry_short.to_dict()
        d["data_requirements"] = list(self.data_requirements)
        d["provenance"] = [p.to_dict() for p in self.provenance]
        return d

    @staticmethod
    def from_dict(d: dict) -> "Hypothesis":
        return Hypothesis(
            id=d["id"], name=d["name"], description=d["description"],
            hypothesis_type=HypothesisType(d["hypothesis_type"]),
            market=d["market"], timeframe=d["timeframe"],
            entry_long=RuleSet.from_dict(d["entry_long"]),
            entry_short=RuleSet.from_dict(d["entry_short"]),
            risk_conditions=d.get("risk_conditions", {}),
            rationale=d["rationale"],
            data_requirements=tuple(d.get("data_requirements", ())),
            status=HypothesisStatus(d.get("status", "draft")),
            created_at=d.get("created_at", datetime.now(timezone.utc).isoformat()),
            version=d.get("version", 1),
            provenance=tuple(
                HypothesisProvenance.from_dict(p) for p in d.get("provenance", [])
            ),
        )


def new_hypothesis_id(name: str) -> str:
    slug = "".join(c.lower() if c.isalnum() else "_" for c in name).strip("_")
    return f"{slug}_{uuid.uuid4().hex[:8]}"
