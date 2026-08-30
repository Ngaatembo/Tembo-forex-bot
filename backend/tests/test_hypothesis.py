import pytest

from app.research.hypothesis import (
    ALLOWED_CONDITION_FIELDS, Condition, Hypothesis, HypothesisStatus, HypothesisType, RuleSet,
    new_hypothesis_id,
)


def test_condition_rejects_unknown_field():
    with pytest.raises(ValueError, match="Unknown condition field"):
        Condition(field="totally_made_up_field", operator=">", value=1.0)


def test_condition_rejects_unknown_operator():
    with pytest.raises(ValueError, match="Unknown operator"):
        Condition(field="rsi_14", operator="~=", value=50.0)


def test_condition_requires_exactly_one_of_value_or_compare_field():
    with pytest.raises(ValueError, match="Exactly one"):
        Condition(field="rsi_14", operator=">", value=50.0, compare_field="close")
    with pytest.raises(ValueError, match="Exactly one"):
        Condition(field="rsi_14", operator=">")


def test_condition_rejects_non_numeric_value():
    with pytest.raises(ValueError, match="numeric"):
        Condition(field="rsi_14", operator=">", value="fifty")  # type: ignore


def test_condition_compare_field_must_also_be_allowed():
    with pytest.raises(ValueError, match="Unknown compare_field"):
        Condition(field="rsi_14", operator=">", compare_field="not_a_real_field")


def test_valid_condition_round_trips_through_dict():
    c = Condition(field="rsi_14", operator=">", value=55.0)
    restored = Condition.from_dict(c.to_dict())
    assert restored == c


def test_condition_field_vs_field_comparison():
    c = Condition(field="sma_10", operator=">", compare_field="sma_50")
    assert c.value is None
    assert c.compare_field == "sma_50"


def test_all_allowed_fields_are_constructible():
    """Every field the module claims to allow should actually work."""
    for f in ALLOWED_CONDITION_FIELDS:
        Condition(field=f, operator=">", value=0.0)


def test_hypothesis_round_trips_through_dict():
    h = Hypothesis(
        id="test_h1", name="Test", description="desc",
        hypothesis_type=HypothesisType.MOMENTUM, market="EUR/USD", timeframe="1h",
        entry_long=RuleSet(conditions=(Condition(field="rsi_14", operator=">", value=55.0),)),
        entry_short=RuleSet(conditions=(Condition(field="rsi_14", operator="<", value=45.0),)),
        risk_conditions={"exit_config": "baseline"}, rationale="testing",
        data_requirements=("rsi_14",),
    )
    restored = Hypothesis.from_dict(h.to_dict())
    assert restored == h


def test_hypothesis_to_dict_is_json_safe():
    """No field should survive to_dict() as anything but str/int/float/bool/list/dict/None."""
    import json
    h = Hypothesis(
        id="test_h2", name="Test", description="desc",
        hypothesis_type=HypothesisType.BREAKOUT, market="EUR/USD", timeframe="1h",
        entry_long=RuleSet(), entry_short=RuleSet(),
        risk_conditions={}, rationale="r", data_requirements=(),
    )
    json.dumps(h.to_dict())  # raises TypeError if anything isn't JSON-safe


def test_new_hypothesis_id_is_unique():
    id1 = new_hypothesis_id("Momentum Test")
    id2 = new_hypothesis_id("Momentum Test")
    assert id1 != id2
    assert "momentum_test" in id1


def test_default_status_is_draft():
    h = Hypothesis(
        id="t3", name="T", description="d", hypothesis_type=HypothesisType.STATISTICAL,
        market="EUR/USD", timeframe="1h", entry_long=RuleSet(), entry_short=RuleSet(),
        risk_conditions={}, rationale="r", data_requirements=(),
    )
    assert h.status == HypothesisStatus.DRAFT
    assert h.version == 1
