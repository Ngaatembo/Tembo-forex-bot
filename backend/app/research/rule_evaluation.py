"""
Evaluates Condition/RuleSet objects against a FeatureSnapshot.

SECURITY: this module contains no dynamic code execution and no
getattr()-based
dynamic dispatch of arbitrary names — field access is a plain, fixed
if/elif against the same closed ALLOWED_CONDITION_FIELDS set enforced
at Condition construction time. There is no code path from a
Hypothesis's data into anything executable.
"""

from app.research.hypothesis import Condition, RuleSet
from app.technical_engine.models import FeatureSnapshot

_OPS = {
    ">": lambda a, b: a > b,
    "<": lambda a, b: a < b,
    ">=": lambda a, b: a >= b,
    "<=": lambda a, b: a <= b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
}


def _get_field(feature: FeatureSnapshot, name: str) -> float | None:
    # Deliberately explicit, not getattr(feature, name) — keeps the set
    # of reachable attributes fixed at review time, not runtime.
    return {
        "close": feature.close, "sma_10": feature.sma_10, "sma_50": feature.sma_50,
        "sma_50_slope": feature.sma_50_slope, "sma_distance": feature.sma_distance,
        "sma_distance_pct": feature.sma_distance_pct, "rsi_14": feature.rsi_14,
        "atr_14": feature.atr_14, "atr_percent": feature.atr_percent,
        "recent_high": feature.recent_high, "recent_low": feature.recent_low,
        "rolling_range": feature.rolling_range,
        "distance_from_high": feature.distance_from_high, "distance_from_low": feature.distance_from_low,
    }[name]


def evaluate_condition(condition: Condition, feature: FeatureSnapshot) -> bool | None:
    """Returns None (not False) if a required field is still in warm-up — an
    unevaluable condition is not the same as a false one."""
    left = _get_field(feature, condition.field)
    right = condition.value if condition.value is not None else _get_field(feature, condition.compare_field)
    if left is None or right is None:
        return None
    return _OPS[condition.operator](left, right)


def evaluate_ruleset(ruleset: RuleSet, feature: FeatureSnapshot) -> bool | None:
    """AND of every condition. None if any condition is unevaluable (warm-up)."""
    if not ruleset.conditions:
        return True
    results = [evaluate_condition(c, feature) for c in ruleset.conditions]
    if any(r is None for r in results):
        return None
    return all(results)
