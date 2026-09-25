from app.paper_trading.validation import run_paper_validation_suite


def test_paper_validation_suite_passes():
    result = run_paper_validation_suite()

    assert result["status"] == "PASS"
    assert result["synthetic"] is True
    assert result["persistent_state_changed"] is False
    assert result["real_broker_contacted"] is False
    assert result["execution_enabled"] is False
    assert len(result["checks"]) == 6
    assert all(check["passed"] for check in result["checks"])
