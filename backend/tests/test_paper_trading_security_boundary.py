"""
Security boundary for app.paper_trading — must have zero path to
execution/broker code, same discipline as every module since Phase 7.
"""

from pathlib import Path

FORBIDDEN_EXECUTION_TOKENS = ["eval(", "exec(", "subprocess", "os.system", "__import__", "compile(", "pickle.loads"]
FORBIDDEN_BROKER_TOKENS = [
    "broker_adapter", "BrokerAdapter", "PaperBrokerAdapter", "get_broker_adapter",
    "app.execution", "MT5", "mt5", "OANDA", "oanda", "place_order",
]

PAPER_TRADING_DIR = Path(__file__).resolve().parent.parent / "app" / "paper_trading"


def test_paper_trading_has_no_execution_or_broker_dependency():
    py_files = [f for f in PAPER_TRADING_DIR.glob("*.py") if f.name != "__init__.py"]
    assert py_files, "expected paper_trading source files to exist"
    for path in py_files:
        content = path.read_text()
        for token in FORBIDDEN_EXECUTION_TOKENS + FORBIDDEN_BROKER_TOKENS:
            assert token not in content, f"{path.name} references '{token}' — a real safety regression."


def test_paper_position_has_no_execute_method():
    from app.paper_trading.models import PaperPosition
    assert not hasattr(PaperPosition, "execute")
    assert not hasattr(PaperPosition, "place_order")
    assert not hasattr(PaperPosition, "send")


def test_engine_cannot_bypass_research_gate_or_risk_engine():
    import inspect
    from app.paper_trading import engine as engine_module
    source = inspect.getsource(engine_module.PaperTradingEngine.evaluate_and_maybe_open)
    assert "select_strategy" in source
    assert "evaluate_risk" in source
