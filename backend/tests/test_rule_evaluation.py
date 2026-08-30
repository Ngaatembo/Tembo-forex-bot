from datetime import datetime, timezone

from app.research.hypothesis import Condition, RuleSet
from app.research.rule_evaluation import evaluate_condition, evaluate_ruleset
from app.technical_engine.models import FeatureSnapshot

BASE = datetime(2024, 1, 8, tzinfo=timezone.utc)


def feat(**overrides) -> FeatureSnapshot:
    defaults = dict(
        timestamp=BASE, close=1.10, sma_10=1.10, sma_50=1.09, sma_50_slope=0.001,
        sma_distance=0.01, sma_distance_pct=0.009, rsi_14=55.0, atr_14=0.001, atr_percent=0.001,
        recent_high=1.11, recent_low=1.08, rolling_range=0.03,
        distance_from_high=0.01, distance_from_low=0.02, regime="RANGING",
    )
    defaults.update(overrides)
    return FeatureSnapshot(**defaults)


def test_evaluate_condition_value_comparison():
    c = Condition(field="rsi_14", operator=">", value=50.0)
    assert evaluate_condition(c, feat(rsi_14=55.0)) is True
    assert evaluate_condition(c, feat(rsi_14=45.0)) is False


def test_evaluate_condition_field_vs_field():
    c = Condition(field="sma_10", operator=">", compare_field="sma_50")
    assert evaluate_condition(c, feat(sma_10=1.10, sma_50=1.09)) is True
    assert evaluate_condition(c, feat(sma_10=1.08, sma_50=1.09)) is False


def test_evaluate_condition_returns_none_during_warmup():
    c = Condition(field="rsi_14", operator=">", value=50.0)
    assert evaluate_condition(c, feat(rsi_14=None)) is None


def test_evaluate_ruleset_ands_all_conditions():
    rs = RuleSet(conditions=(
        Condition(field="rsi_14", operator=">", value=50.0),
        Condition(field="close", operator=">", compare_field="sma_50"),
    ))
    assert evaluate_ruleset(rs, feat(rsi_14=55.0, close=1.10, sma_50=1.09)) is True
    assert evaluate_ruleset(rs, feat(rsi_14=45.0, close=1.10, sma_50=1.09)) is False


def test_evaluate_ruleset_none_if_any_condition_unevaluable():
    rs = RuleSet(conditions=(
        Condition(field="rsi_14", operator=">", value=50.0),
        Condition(field="atr_14", operator=">", value=0.0005),
    ))
    result = evaluate_ruleset(rs, feat(rsi_14=55.0, atr_14=None))
    assert result is None


def test_empty_ruleset_is_always_true():
    assert evaluate_ruleset(RuleSet(), feat()) is True
