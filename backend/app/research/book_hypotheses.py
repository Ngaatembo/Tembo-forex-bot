"""
Structured, non-executable bridge from registered book claims to testable
Tembo research hypotheses.

These specifications are research inputs only. They do not emit signals,
place orders, or bypass the deterministic rule evaluator. Candlestick
claims are represented as explicit evidence requirements because the
numeric Condition schema intentionally does not encode candle-shape
semantics.
"""

from dataclasses import asdict, dataclass
from pathlib import Path
import json


@dataclass(frozen=True)
class EvidenceRequirement:
    kind: str
    pattern: str
    direction: str
    confirmation_required: bool
    context: str

    def __post_init__(self):
        if self.kind != "candlestick_pattern":
            raise ValueError("Unsupported evidence requirement kind.")
        if not self.pattern.strip():
            raise ValueError("pattern must not be empty.")
        if self.direction not in {"BULLISH", "BEARISH", "NEUTRAL"}:
            raise ValueError("direction must be BULLISH, BEARISH, or NEUTRAL.")
        if not self.context.strip():
            raise ValueError("context must not be empty.")

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class BookHypothesisSpec:
    hypothesis_id: str
    claim_id: str
    source_id: str
    name: str
    objective: str
    evidence: tuple[EvidenceRequirement, ...]
    profitability_status: str = "UNVALIDATED"

    def __post_init__(self):
        for value, field_name in (
            (self.hypothesis_id, "hypothesis_id"),
            (self.claim_id, "claim_id"),
            (self.source_id, "source_id"),
            (self.name, "name"),
            (self.objective, "objective"),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} must not be empty.")
        if not self.evidence:
            raise ValueError("A book hypothesis must contain at least one evidence requirement.")
        if self.profitability_status != "UNVALIDATED":
            raise ValueError("Book-derived hypotheses cannot be marked validated by this bridge.")

    def to_dict(self) -> dict:
        d = asdict(self)
        d["evidence"] = [item.to_dict() for item in self.evidence]
        return d


def build_book_hypotheses() -> tuple[BookHypothesisSpec, ...]:
    return (
        BookHypothesisSpec(
            "BOOK_CANDLE_DOJI_CONTEXT",
            "CANDLE_001",
            "BOOK_CANDLESTICK_MATERIAL",
            "Doji contextual evidence",
            "Test whether a doji provides useful contextual information when combined with independent market-state evidence.",
            (EvidenceRequirement("candlestick_pattern", "DOJI", "NEUTRAL", False, "contextual"),),
        ),
        BookHypothesisSpec(
            "BOOK_CANDLE_HAMMER_CONTEXT",
            "CANDLE_002",
            "BOOK_CANDLESTICK_MATERIAL",
            "Hammer and Hanging Man contextual reversal evidence",
            "Test reversal evidence only with the required prior-trend context and confirmation.",
            (
                EvidenceRequirement("candlestick_pattern", "HAMMER", "BULLISH", True, "DOWN"),
                EvidenceRequirement("candlestick_pattern", "HANGING_MAN", "BEARISH", True, "UP"),
            ),
        ),
        BookHypothesisSpec(
            "BOOK_CANDLE_SHOOTING_STAR_CONTEXT",
            "CANDLE_003",
            "BOOK_CANDLESTICK_MATERIAL",
            "Shooting Star and Inverted Hammer contextual reversal evidence",
            "Test reversal evidence only with prior-trend context and confirmation.",
            (
                EvidenceRequirement("candlestick_pattern", "SHOOTING_STAR", "BEARISH", True, "UP"),
                EvidenceRequirement("candlestick_pattern", "INVERTED_HAMMER", "BULLISH", True, "DOWN"),
            ),
        ),
        BookHypothesisSpec(
            "BOOK_CANDLE_ENGULFING_CONTEXT",
            "CANDLE_004",
            "BOOK_CANDLESTICK_MATERIAL",
            "Engulfing contextual reversal evidence",
            "Test bullish and bearish engulfing as contextual evidence rather than standalone authorization.",
            (
                EvidenceRequirement("candlestick_pattern", "BULLISH_ENGULFING", "BULLISH", False, "DOWN"),
                EvidenceRequirement("candlestick_pattern", "BEARISH_ENGULFING", "BEARISH", False, "UP"),
            ),
        ),
        BookHypothesisSpec(
            "BOOK_CANDLE_THREE_CANDLE_REVERSAL",
            "CANDLE_005",
            "BOOK_CANDLESTICK_MATERIAL",
            "Three-candle reversal contextual evidence",
            "Test Morning Star and Evening Star as contextual multi-candle evidence.",
            (
                EvidenceRequirement("candlestick_pattern", "MORNING_STAR", "BULLISH", False, "contextual"),
                EvidenceRequirement("candlestick_pattern", "EVENING_STAR", "BEARISH", False, "contextual"),
            ),
        ),
    )


def write_registry(path: str | Path) -> None:
    payload = {
        "schema_version": 1,
        "purpose": "Structured research hypotheses derived from registered book claims; all profitability remains unvalidated.",
        "hypotheses": [h.to_dict() for h in build_book_hypotheses()],
    }
    Path(path).write_text(json.dumps(payload, indent=2) + "\n")
