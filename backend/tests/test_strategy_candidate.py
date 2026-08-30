import dataclasses

import pytest

from app.research.hypothesis import HypothesisType
from app.research.strategy_candidate import (
    StrategyCandidate, load_candidates, new_candidate_id, save_candidate,
    validate_experiment_ids_exist,
)


def make_candidate(**overrides) -> StrategyCandidate:
    defaults = dict(
        candidate_id="cand_test123", name="Test Candidate",
        family=HypothesisType.MEAN_REVERSION, description="A test candidate.",
        experiment_ids=("exp_abc123",), parent_candidate_id=None,
        lineage_note=None, research_priority=None, gate_status=None,
        created_at="2026-01-01T00:00:00+00:00",
    )
    defaults.update(overrides)
    return StrategyCandidate(**defaults)


def test_valid_candidate_constructs():
    c = make_candidate()
    assert c.candidate_id == "cand_test123"
    assert c.family == HypothesisType.MEAN_REVERSION
    assert c.experiment_ids == ("exp_abc123",)


def test_invalid_family_rejected():
    with pytest.raises(ValueError):
        StrategyCandidate(
            candidate_id="c1", name="x", family="not_a_real_family",  # type: ignore
            description="x", experiment_ids=("exp_1",), parent_candidate_id=None,
            lineage_note=None, research_priority=None, gate_status=None,
            created_at="2026-01-01T00:00:00+00:00",
        )


def test_empty_experiment_ids_rejected():
    """A candidate must reference at least one real experiment — it
    can't exist as pure, evidence-free speculation."""
    with pytest.raises(ValueError):
        make_candidate(experiment_ids=())


def test_experiment_ids_must_be_strings():
    with pytest.raises(ValueError):
        make_candidate(experiment_ids=(123,))  # type: ignore


def test_lineage_parent_recorded():
    parent = make_candidate(candidate_id="cand_parent")
    child = make_candidate(
        candidate_id="cand_child", parent_candidate_id=parent.candidate_id,
        lineage_note="Robustness follow-up to cand_parent.",
    )
    assert child.parent_candidate_id == "cand_parent"
    assert "follow-up" in child.lineage_note


def test_missing_experiment_flagged_by_validator():
    """validate_experiment_ids_exist is a SEPARATE function, not baked
    into the dataclass constructor — the candidate itself does no I/O.
    This keeps StrategyCandidate a pure, testable data object."""
    c = make_candidate(experiment_ids=("exp_real", "exp_does_not_exist"))
    known_experiment_ids = {"exp_real"}
    missing = validate_experiment_ids_exist(c, known_experiment_ids)
    assert missing == ["exp_does_not_exist"]


def test_missing_experiment_validator_empty_when_all_exist():
    c = make_candidate(experiment_ids=("exp_real",))
    assert validate_experiment_ids_exist(c, {"exp_real"}) == []


def test_serialization_round_trip():
    c = make_candidate(parent_candidate_id="cand_parent", lineage_note="test note")
    d = c.to_dict()
    assert d["family"] == "mean_reversion"  # enum -> plain string for JSON
    restored = StrategyCandidate.from_dict(d)
    assert restored == c


def test_candidate_is_immutable():
    c = make_candidate()
    with pytest.raises(dataclasses.FrozenInstanceError):
        c.name = "changed"  # type: ignore


def test_new_candidate_id_is_unique():
    a = new_candidate_id("range extreme reversion")
    b = new_candidate_id("range extreme reversion")
    assert a != b
    assert a.startswith("cand_")


def test_save_and_load_candidates_append_only(tmp_path):
    registry_path = str(tmp_path / "candidates.json")
    first = make_candidate(candidate_id="cand_1")
    second = make_candidate(candidate_id="cand_2", name="Second")

    save_candidate(first, registry_path)
    save_candidate(second, registry_path)

    loaded = load_candidates(registry_path)
    assert len(loaded) == 2
    assert {c.candidate_id for c in loaded} == {"cand_1", "cand_2"}


def test_load_candidates_empty_registry_returns_empty_list(tmp_path):
    registry_path = str(tmp_path / "does_not_exist.json")
    assert load_candidates(registry_path) == []
