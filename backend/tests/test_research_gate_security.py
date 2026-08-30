"""
Source-level security scan for research_gate.py specifically —
extends the same discipline as test_research_security_boundary.py
(which already covers app/research/*.py generally) with an explicit,
named check for this module, so a future edit can't silently
introduce an execution/broker path without a test catching it.
"""

from pathlib import Path

FORBIDDEN_EXECUTION_TOKENS = ["eval(", "exec(", "subprocess", "os.system", "__import__", "compile(", "pickle.loads"]
FORBIDDEN_BROKER_TOKENS = ["broker_adapter", "BrokerAdapter", "app.execution", "app.risk_engine", "place_order"]


def test_research_gate_has_no_execution_or_broker_dependency():
    path = Path(__file__).resolve().parent.parent / "app" / "research" / "research_gate.py"
    content = path.read_text()
    for token in FORBIDDEN_EXECUTION_TOKENS + FORBIDDEN_BROKER_TOKENS:
        assert token not in content, f"research_gate.py references '{token}' — a real safety regression."
