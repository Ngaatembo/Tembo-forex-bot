"""
Source-level security scan for family_saturation.py and
research_priority.py specifically — same discipline as
test_research_gate_security.py.
"""

from pathlib import Path

FORBIDDEN_EXECUTION_TOKENS = ["eval(", "exec(", "subprocess", "os.system", "__import__", "compile(", "pickle.loads"]
FORBIDDEN_BROKER_TOKENS = ["broker_adapter", "BrokerAdapter", "app.execution", "app.risk_engine", "place_order"]


def test_family_saturation_and_priority_have_no_execution_or_broker_dependency():
    research_dir = Path(__file__).resolve().parent.parent / "app" / "research"
    for filename in ("family_saturation.py", "research_priority.py"):
        content = (research_dir / filename).read_text()
        for token in FORBIDDEN_EXECUTION_TOKENS + FORBIDDEN_BROKER_TOKENS:
            assert token not in content, f"{filename} references '{token}' — a real safety regression."
