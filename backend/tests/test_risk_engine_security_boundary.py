"""
Security boundary for the Phase 15 Risk Engine — must have zero path
to execution/broker code. Same discipline as every research module's
security test since Phase 7.
"""

from pathlib import Path

FORBIDDEN_EXECUTION_TOKENS = ["eval(", "exec(", "subprocess", "os.system", "__import__", "compile(", "pickle.loads"]
FORBIDDEN_BROKER_TOKENS = [
    "broker_adapter", "BrokerAdapter", "PaperBrokerAdapter", "get_broker_adapter",
    "app.execution", "MT5", "mt5", "place_order",
]

RISK_ENGINE_DIR = Path(__file__).resolve().parent.parent / "app" / "risk_engine"


def test_risk_engine_has_no_execution_or_broker_dependency():
    py_files = [f for f in RISK_ENGINE_DIR.glob("*.py") if f.name != "__init__.py"]
    assert py_files, "expected risk_engine source files to exist"
    for path in py_files:
        content = path.read_text()
        for token in FORBIDDEN_EXECUTION_TOKENS + FORBIDDEN_BROKER_TOKENS:
            assert token not in content, f"{path.name} references '{token}' — a real safety regression."


def test_risk_decision_is_pure_data_no_execute_method():
    from app.risk_engine.risk_models import RiskDecision
    assert not hasattr(RiskDecision, "execute")
    assert not hasattr(RiskDecision, "place_order")
    assert not hasattr(RiskDecision, "send")
