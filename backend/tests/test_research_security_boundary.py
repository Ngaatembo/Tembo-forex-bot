"""
Proves, at the source-code level, that the research intelligence
engine (Phase 7) cannot execute arbitrary code and cannot reach the
broker adapter — the two guarantees this whole phase depends on.
"""

from pathlib import Path

RESEARCH_DIR = Path(__file__).resolve().parent.parent / "app" / "research"

FORBIDDEN_EXECUTION_TOKENS = [
    "eval(", "exec(", "subprocess", "os.system", "__import__", "compile(", "pickle.loads",
]
FORBIDDEN_BROKER_TOKENS = ["broker_adapter", "BrokerAdapter", "PaperBrokerAdapter", "get_broker_adapter"]


def _all_research_py_files() -> list[Path]:
    files = list(RESEARCH_DIR.glob("*.py"))
    assert files, "expected research module source files to exist"
    return files


def test_no_arbitrary_code_execution_anywhere_in_research_module():
    for path in _all_research_py_files():
        content = path.read_text()
        for token in FORBIDDEN_EXECUTION_TOKENS:
            assert token not in content, (
                f"{path} contains '{token}' — the research engine must never be able to "
                "execute arbitrary code from a hypothesis or AI proposal."
            )


def test_research_module_never_references_broker_adapter():
    for path in _all_research_py_files():
        content = path.read_text()
        for token in FORBIDDEN_BROKER_TOKENS:
            assert token not in content, f"{path} references '{token}' — research must stay execution-isolated."


def test_hypothesis_condition_fields_are_a_closed_allowlist():
    """Structural proof that Condition can only ever reference a fixed,
    known set of fields — not an open string that could later be abused."""
    from app.research.hypothesis import ALLOWED_CONDITION_FIELDS

    assert isinstance(ALLOWED_CONDITION_FIELDS, frozenset)
    assert len(ALLOWED_CONDITION_FIELDS) > 0
    # every field must be a plain lowercase identifier — no dotted paths,
    # no dunder attributes, nothing that could reach outside a flat namespace
    for f in ALLOWED_CONDITION_FIELDS:
        assert f.isidentifier() and not f.startswith("_")


def test_ai_proposal_cannot_smuggle_code_via_any_key():
    """End-to-end proof, not just a static scan: feeding a proposal
    containing an execution-flavored key is rejected before a Hypothesis
    is ever constructed."""
    import pytest
    from app.research.ai_interface import parse_ai_proposal

    malicious = {
        "name": "x", "description": "x", "hypothesis_type": "momentum",
        "market": "EUR/USD", "timeframe": "1h", "entry_long": [], "entry_short": [],
        "rationale": "x", "exec": "os.system('echo pwned')",
    }
    with pytest.raises(ValueError):
        parse_ai_proposal(malicious)


def test_research_api_has_only_get_endpoints():
    """Structural proof: no POST/PUT/DELETE exists anywhere on the
    research router — nothing can create, modify, or execute anything
    through the API."""
    from app.api.routes.research import router

    for route in router.routes:
        methods = getattr(route, "methods", set())
        assert methods <= {"GET", "HEAD"}, f"{route.path} exposes non-GET method(s): {methods}"


def test_breakout_strategy_has_no_execution_or_code_execution_dependency():
    """
    Phase 9 extension: strategy_engine/breakout.py lives outside
    app/research/ and app/backtesting/ (it's signal-generation code,
    same category as crossover.py), so it isn't covered by the scans
    above — this closes that gap explicitly rather than relying on
    breakout.py happening to be clean by accident.
    """
    breakout_path = Path(__file__).resolve().parent.parent / "app" / "strategy_engine" / "breakout.py"
    content = breakout_path.read_text()
    for token in FORBIDDEN_EXECUTION_TOKENS + FORBIDDEN_BROKER_TOKENS:
        assert token not in content, f"breakout.py references '{token}' — a real safety regression."
