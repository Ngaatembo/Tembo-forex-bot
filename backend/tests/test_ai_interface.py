import pytest

from app.research.ai_interface import parse_ai_proposal
from app.research.hypothesis import Hypothesis


def valid_proposal(**overrides) -> dict:
    base = {
        "name": "Momentum Idea",
        "description": "RSI-based momentum entry",
        "hypothesis_type": "momentum",
        "market": "EUR/USD",
        "timeframe": "1h",
        "entry_long": [{"field": "rsi_14", "operator": ">", "value": 60.0}],
        "entry_short": [{"field": "rsi_14", "operator": "<", "value": 40.0}],
        "rationale": "momentum persists short-term",
    }
    base.update(overrides)
    return base


def test_valid_proposal_parses_into_hypothesis():
    h = parse_ai_proposal(valid_proposal())
    assert isinstance(h, Hypothesis)
    assert h.name == "Momentum Idea"
    assert len(h.entry_long.conditions) == 1


def test_rejects_forbidden_code_key():
    proposal = valid_proposal()
    proposal["code"] = "import os; os.system('rm -rf /')"
    with pytest.raises(ValueError, match="forbidden"):
        parse_ai_proposal(proposal)


def test_rejects_forbidden_eval_key():
    proposal = valid_proposal()
    proposal["eval"] = "1+1"
    with pytest.raises(ValueError, match="forbidden"):
        parse_ai_proposal(proposal)


def test_rejects_expression_key_smuggling_attempt():
    proposal = valid_proposal()
    proposal["expression"] = "close > sma_50 and __import__('os').system('ls')"
    with pytest.raises(ValueError, match="forbidden"):
        parse_ai_proposal(proposal)


def test_rejects_missing_required_key():
    proposal = valid_proposal()
    del proposal["rationale"]
    with pytest.raises(ValueError, match="missing"):
        parse_ai_proposal(proposal)


def test_rejects_unknown_hypothesis_type():
    proposal = valid_proposal(hypothesis_type="quantum_prediction")
    with pytest.raises(ValueError, match="Unknown hypothesis_type"):
        parse_ai_proposal(proposal)


def test_rejects_condition_with_unknown_field():
    proposal = valid_proposal(entry_long=[{"field": "moon_phase", "operator": ">", "value": 1.0}])
    with pytest.raises(ValueError, match="Unknown condition field"):
        parse_ai_proposal(proposal)


def test_rejects_condition_with_extra_unexpected_key():
    proposal = valid_proposal(
        entry_long=[{"field": "rsi_14", "operator": ">", "value": 60.0, "injected_code": "os.system('x')"}]
    )
    with pytest.raises(ValueError, match="unexpected keys"):
        parse_ai_proposal(proposal)


def test_rejects_non_dict_proposal():
    with pytest.raises(ValueError, match="must be a dict"):
        parse_ai_proposal("not a dict at all")  # type: ignore


def test_rejects_entry_long_not_a_list():
    proposal = valid_proposal(entry_long="close > 1.10")  # a raw string expression attempt
    with pytest.raises(ValueError, match="must be a list"):
        parse_ai_proposal(proposal)


def test_each_generated_hypothesis_has_a_unique_id():
    h1 = parse_ai_proposal(valid_proposal())
    h2 = parse_ai_proposal(valid_proposal())
    assert h1.id != h2.id
