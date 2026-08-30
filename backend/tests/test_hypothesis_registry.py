import pytest

from app.research.hypothesis import Hypothesis, HypothesisType, RuleSet
from app.research.hypothesis_registry import (
    get_hypothesis, list_hypotheses, register_hypothesis, version_hypothesis,
)


def make_hypothesis(id_: str) -> Hypothesis:
    return Hypothesis(
        id=id_, name="Test", description="d", hypothesis_type=HypothesisType.MOMENTUM,
        market="EUR/USD", timeframe="1h", entry_long=RuleSet(), entry_short=RuleSet(),
        risk_conditions={}, rationale="r", data_requirements=(),
    )


def test_register_and_get(tmp_path):
    registry = str(tmp_path / "registry.json")
    h = make_hypothesis("h1")
    register_hypothesis(h, registry)
    retrieved = get_hypothesis("h1", registry)
    assert retrieved == h


def test_register_duplicate_id_raises(tmp_path):
    registry = str(tmp_path / "registry.json")
    register_hypothesis(make_hypothesis("h1"), registry)
    with pytest.raises(ValueError, match="already registered"):
        register_hypothesis(make_hypothesis("h1"), registry)


def test_get_missing_hypothesis_returns_none(tmp_path):
    registry = str(tmp_path / "registry.json")
    assert get_hypothesis("nonexistent", registry) is None


def test_version_hypothesis_creates_new_version_never_overwrites(tmp_path):
    registry = str(tmp_path / "registry.json")
    original = make_hypothesis("h1")
    register_hypothesis(original, registry)

    updated = version_hypothesis("h1", registry, description="revised description")

    assert updated.version == 2
    assert updated.description == "revised description"

    # the original version 1 record must still be retrievable, untouched
    v1 = get_hypothesis("h1", registry, version=1)
    assert v1.description == "d"
    assert v1.version == 1

    latest = get_hypothesis("h1", registry)
    assert latest.version == 2


def test_list_hypotheses_returns_latest_by_default(tmp_path):
    registry = str(tmp_path / "registry.json")
    register_hypothesis(make_hypothesis("h1"), registry)
    register_hypothesis(make_hypothesis("h2"), registry)
    version_hypothesis("h1", registry, description="v2 desc")

    latest = list_hypotheses(registry, latest_only=True)
    assert len(latest) == 2
    h1_latest = next(h for h in latest if h.id == "h1")
    assert h1_latest.version == 2


def test_list_hypotheses_all_versions(tmp_path):
    registry = str(tmp_path / "registry.json")
    register_hypothesis(make_hypothesis("h1"), registry)
    version_hypothesis("h1", registry, description="v2")
    all_records = list_hypotheses(registry, latest_only=False)
    assert len(all_records) == 2


def test_version_nonexistent_hypothesis_raises(tmp_path):
    registry = str(tmp_path / "registry.json")
    with pytest.raises(ValueError, match="No hypothesis"):
        version_hypothesis("ghost", registry, description="x")


def test_empty_registry_file_handled(tmp_path):
    registry = str(tmp_path / "does_not_exist_yet.json")
    assert list_hypotheses(registry) == []
    assert get_hypothesis("anything", registry) is None
