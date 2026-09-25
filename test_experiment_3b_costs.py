"""Guards the Experiment 3B finding: gold must never again be tested with forex-sized costs."""

import ast
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "run_experiment_3b_gold_real_costs.py"


def _cost_tiers():
    tree = ast.parse(SCRIPT.read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "COST_TIERS" for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError("COST_TIERS not found")


def test_gold_cost_tiers_are_in_dollars_per_ounce():
    tiers = _cost_tiers()
    for name in ("LOW", "BASE", "HIGH"):
        # Real XAU/USD spreads are roughly $0.15–$0.60/oz. Anything under $0.10 is the old forex-scale bug.
        assert tiers[name]["spread"] >= 0.10, f"{name} gold spread {tiers[name]['spread']} is forex-scale"
    assert tiers["LOW"]["spread"] < tiers["BASE"]["spread"] < tiers["HIGH"]["spread"]


def test_original_tier_kept_only_for_comparison():
    tiers = _cost_tiers()
    assert tiers["ORIGINAL_FOREX_TIER"]["spread"] < 0.001


def test_experiment_script_has_no_broker_or_execution_dependency():
    content = SCRIPT.read_text().lower()
    for token in ("broker", "live_execution", "place_order", "oanda_api"):
        assert token not in content
