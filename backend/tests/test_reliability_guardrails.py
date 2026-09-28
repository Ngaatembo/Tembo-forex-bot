from app.reliability.guardrails import (
    detect_drift,
    drawdown_governor,
    evaluate_cost_gate,
    monte_carlo_trade_resample,
)


def test_cost_gate_blocks_expensive_trade():
    result = evaluate_cost_gate(100.0, 99.0, 100.5, 0.2)
    assert result.status == "BLOCK"


def test_cost_gate_passes_reasonable_cost():
    result = evaluate_cost_gate(100.0, 99.0, 102.0, 0.1)
    assert result.status == "PASS"


def test_drawdown_governor_halts_at_limit():
    assert drawdown_governor(15.0).status == "HALT"


def test_drawdown_governor_scales_at_warning():
    result = drawdown_governor(7.0)
    assert result.status == "WARNING"
    assert result.size_multiplier == 0.5


def test_drift_requires_sufficient_data():
    assert detect_drift([1.0] * 5, [1.0] * 5).status == "INSUFFICIENT_DATA"


def test_drift_detects_material_change():
    result = detect_drift([1.0] * 20, [1.3] * 20)
    assert result.status == "DRIFT"


def test_monte_carlo_is_deterministic():
    result = monte_carlo_trade_resample([1.0, -0.5] * 20, simulations=100)
    assert result.simulations == 100
    assert result.median_return != 0
