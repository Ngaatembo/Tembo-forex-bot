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


def test_risk_engine_uses_central_kill_switch(monkeypatch):
    from app.risk_engine import risk_engine
    from app.risk_engine.risk_models import AccountState, RiskLimitsConfig
    from app.research.strategy_selector import SelectionResult

    calls = []
    original_check = risk_engine.check_kill_switch

    def fake_check(*, kill_switch_active, manually_triggered=False):
        calls.append((kill_switch_active, manually_triggered))
        return original_check(
            kill_switch_active=kill_switch_active,
            manually_triggered=manually_triggered,
        )

    monkeypatch.setattr(risk_engine, "check_kill_switch", fake_check)

    account = AccountState(
        equity=10000,
        peak_equity=10000,
        daily_start_equity=10000,
        kill_switch_active=True,
    )
    selection = SelectionResult(
        instrument="XAU/USD",
        timeframe="h1",
        status="TRADEABLE",
        selected_config_id="test-config",
        reason="test",
        considered=(),
        research_recommendation=None,
    )
    result = risk_engine.evaluate_risk(
        selection_result=selection,
        account=account,
        limits=RiskLimitsConfig(),
    )
    assert result.state == "KILL_SWITCH_ACTIVE"
    assert calls == [(True, False)]


def test_account_data_rejects_non_finite_values():
    from math import nan
    from app.risk_engine.account_limits import account_data_valid
    from app.risk_engine.risk_models import AccountState

    for account in (
        AccountState(equity=nan, peak_equity=10000, daily_start_equity=10000, kill_switch_active=False),
        AccountState(equity=10000, peak_equity=nan, daily_start_equity=10000, kill_switch_active=False),
        AccountState(equity=10000, peak_equity=10000, daily_start_equity=nan, kill_switch_active=False),
    ):
        valid, _ = account_data_valid(account)
        assert not valid


def test_stop_validation_rejects_non_finite_prices():
    from math import inf, nan
    from app.risk_engine.stop_validation import validate_stop

    assert not validate_stop("LONG", nan, 1.0).valid
    assert not validate_stop("LONG", 1.0, inf).valid


def test_risk_limits_reject_non_finite_values():
    from math import nan
    from app.risk_engine.risk_models import RiskLimitsConfig

    try:
        RiskLimitsConfig(max_risk_per_trade_pct=nan)
    except ValueError:
        return
    raise AssertionError("non-finite risk configuration must be rejected")
