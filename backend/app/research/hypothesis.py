"""
Structured research hypothesis model.

SECURITY-CRITICAL DESIGN PRINCIPLE: a Hypothesis can only ever contain
JSON-safe data — strings, numbers, and Condition objects built from a
closed, validated set of feature names and comparison operators. There
is no field anywhere in this model that can hold a Python expression,
a callable, a SQL string, or any other executable payload. This is
what makes "AI proposes, deterministic engine evaluates" safe: even a
malicious or broken AI proposal can only ever produce data that either
validates into this narrow schema or is rejected — it can never
produce code that runs.

See rule_evaluation.py for the evaluator (also free of any eval-style dynamic execution)
evaluator that turns a RuleSet into a boolean per candle.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum

# The ONLY feature fields a condition may reference — deliberately a
# closed allowlist (Phase 5's FeatureSnapshot fields), not an open
# string. Any condition naming a field outside this set is rejected at
# construction time, before it ever reaches an evaluator.
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
    """
    One deterministic comparison: field OP value, or field OP compare_field.
    Exactly one of `value` / `compare_field` must be set — never both,
    never neither. This is the ONLY way a threshold enters the system;
    there is no free-text expression field anywhere in this dataclass.
    """
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
class Hypothesis:
    id: str
    name: str
    description: str
    hypothesis_type: HypothesisType
    market: str
    timeframe: str
    entry_long: RuleSet
    entry_short: RuleSet
    risk_conditions: dict  # small JSON-safe dict, e.g. {"exit_config": "baseline"} — no code
    rationale: str
    data_requirements: tuple[str, ...]
    status: HypothesisStatus = HypothesisStatus.DRAFT
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    version: int = 1

    def to_dict(self) -> dict:
        d = asdict(self)
        d["hypothesis_type"] = self.hypothesis_type.value
        d["status"] = self.status.value
        d["entry_long"] = self.entry_long.to_dict()
        d["entry_short"] = self.entry_short.to_dict()
        d["data_requirements"] = list(self.data_requirements)
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
        )


def new_hypothesis_id(name: str) -> str:
    slug = "".join(c.lower() if c.isalnum() else "_" for c in name).strip("_")
    return f"{slug}_{uuid.uuid4().hex[:8]}"
