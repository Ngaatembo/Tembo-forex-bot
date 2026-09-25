import json

import pytest

from app.research.hypothesis import (
    Hypothesis,
    HypothesisProvenance,
    HypothesisType,
    RuleSet,
)
from app.research.hypothesis_registry import register_hypothesis, get_hypothesis


def make_hypothesis(id_: str, provenance=()) -> Hypothesis:
    return Hypothesis(
        id=id_, name="Test", description="d", hypothesis_type=HypothesisType.MOMENTUM,
        market="EUR/USD", timeframe="1h", entry_long=RuleSet(), entry_short=RuleSet(),
        risk_conditions={}, rationale="r", data_requirements=(), provenance=provenance,
    )


def test_provenance_round_trips_without_changing_rule_data():
    provenance = (
        HypothesisProvenance(
            source_id="market_wizards",
            claim_id="MW_001",
            mapping_note="Test practitioner-method diversity as a hypothesis; do not treat it as a signal.",
        ),
    )
    hypothesis = make_hypothesis("h1", provenance)
    encoded = hypothesis.to_dict()

    assert encoded["provenance"] == [{
        "source_id": "market_wizards",
        "claim_id": "MW_001",
        "mapping_note": "Test practitioner-method diversity as a hypothesis; do not treat it as a signal.",
    }]
    assert encoded["entry_long"] == {"conditions": []}
    assert encoded["entry_short"] == {"conditions": []}

    decoded = Hypothesis.from_dict(encoded)
    assert decoded == hypothesis


def test_legacy_hypothesis_without_provenance_loads_with_empty_metadata():
    hypothesis = make_hypothesis("legacy")
    legacy = hypothesis.to_dict()
    legacy.pop("provenance")

    decoded = Hypothesis.from_dict(legacy)

    assert decoded.provenance == ()
    assert decoded.entry_long == hypothesis.entry_long
    assert decoded.entry_short == hypothesis.entry_short


def test_registry_preserves_provenance_across_round_trip(tmp_path):
    registry = str(tmp_path / "registry.json")
    provenance = (
        HypothesisProvenance("cme_position_size", "CME_001", "Use as risk-management context only."),
    )
    hypothesis = make_hypothesis("h1", provenance)

    register_hypothesis(hypothesis, registry)
    stored = json.loads((tmp_path / "registry.json").read_text())

    assert stored[0]["provenance"][0]["claim_id"] == "CME_001"
    assert get_hypothesis("h1", registry) == hypothesis


def test_provenance_rejects_blank_metadata():
    with pytest.raises(ValueError, match="source_id"):
        HypothesisProvenance("", "C1", "note")
    with pytest.raises(ValueError, match="claim_id"):
        HypothesisProvenance("S1", "", "note")
    with pytest.raises(ValueError, match="mapping_note"):
        HypothesisProvenance("S1", "C1", " ")
