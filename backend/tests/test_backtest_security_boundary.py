"""
Test 31 — verifies at the source-code level that no file in the
backtesting engine or its API route imports or references the broker
adapter. This is checked directly rather than just by convention,
because a future edit accidentally wiring the two together would be
a serious safety regression — a backtest must never be able to place
a real or even paper broker order.
"""

from pathlib import Path

BACKTESTING_DIR = Path(__file__).resolve().parent.parent / "app" / "backtesting"
RESEARCH_DIR = Path(__file__).resolve().parent.parent / "app" / "research"
BACKTEST_ROUTE = Path(__file__).resolve().parent.parent / "app" / "api" / "routes" / "backtest.py"

FORBIDDEN_TOKENS = ["broker_adapter", "BrokerAdapter", "PaperBrokerAdapter", "get_broker_adapter"]


def test_backtesting_module_never_references_broker_adapter():
    py_files = list(BACKTESTING_DIR.glob("*.py")) + list(RESEARCH_DIR.glob("*.py")) + [BACKTEST_ROUTE]
    assert py_files, "expected backtesting source files to exist"

    for path in py_files:
        content = path.read_text()
        for token in FORBIDDEN_TOKENS:
            assert token not in content, (
                f"{path} references '{token}' — the backtesting/research engine must never "
                "touch the broker adapter. This is a safety regression."
            )
