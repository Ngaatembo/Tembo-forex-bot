from app.risk_engine.kill_switch import RiskState, check_kill_switch


def test_kill_switch_defaults_to_blocked():
    result = check_kill_switch()
    assert result.state == RiskState.BLOCKED
    assert result.allowed is False


def test_kill_switch_manual_trigger_blocks():
    result = check_kill_switch(manually_triggered=True)
    assert result.state == RiskState.BLOCKED
    assert result.allowed is False
