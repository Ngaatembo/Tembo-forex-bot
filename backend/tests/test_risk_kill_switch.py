from app.risk_engine.kill_switch import RiskState, check_kill_switch


def test_kill_switch_active_blocks():
    result = check_kill_switch(kill_switch_active=True)
    assert result.state == RiskState.BLOCKED
    assert result.allowed is False


def test_kill_switch_manual_trigger_blocks():
    result = check_kill_switch(kill_switch_active=False, manually_triggered=True)
    assert result.state == RiskState.BLOCKED
    assert result.allowed is False


def test_kill_switch_inactive_allows():
    """New real behavior — the Phase 0 placeholder could never do this,
    since it always returned BLOCKED regardless of input."""
    result = check_kill_switch(kill_switch_active=False)
    assert result.state == RiskState.OK
    assert result.allowed is True


def test_kill_switch_active_requires_explicit_argument():
    """No default — a caller cannot accidentally get a 'safe by omission' result."""
    import pytest
    with pytest.raises(TypeError):
        check_kill_switch()
