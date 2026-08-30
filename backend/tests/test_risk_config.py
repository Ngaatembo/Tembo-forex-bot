import pytest

from app.backtesting.risk_config import RiskConfig, compute_position_size, drawdown_halt_triggered


def test_fixed_sizing_returns_configured_size():
    config = RiskConfig(model="fixed", fixed_size=10_000)
    size = compute_position_size(config=config, current_equity=5000, entry_price=1.10, stop_price=None)
    assert size == 10_000


def test_fixed_model_requires_positive_size():
    with pytest.raises(ValueError):
        RiskConfig(model="fixed", fixed_size=0)
    with pytest.raises(ValueError):
        RiskConfig(model="fixed")


def test_percent_of_equity_sizing_hand_verified():
    # risk 1% of $10,000 = $100; stop distance = 0.0050 -> size = 100/0.005 = 20,000
    config = RiskConfig(model="percent_of_equity", risk_pct_of_equity=0.01)
    size = compute_position_size(
        config=config, current_equity=10_000, entry_price=1.1000, stop_price=1.0950,
    )
    assert size == pytest.approx(20_000)


def test_percent_of_equity_requires_valid_pct():
    with pytest.raises(ValueError):
        RiskConfig(model="percent_of_equity", risk_pct_of_equity=0)
    with pytest.raises(ValueError):
        RiskConfig(model="percent_of_equity", risk_pct_of_equity=1.5)


def test_percent_of_equity_fails_closed_without_stop():
    config = RiskConfig(model="percent_of_equity", risk_pct_of_equity=0.01)
    size = compute_position_size(config=config, current_equity=10_000, entry_price=1.10, stop_price=None)
    assert size == 0.0


def test_percent_of_equity_fails_closed_on_zero_stop_distance():
    config = RiskConfig(model="percent_of_equity", risk_pct_of_equity=0.01)
    size = compute_position_size(config=config, current_equity=10_000, entry_price=1.10, stop_price=1.10)
    assert size == 0.0


def test_max_position_size_caps_fixed_sizing():
    config = RiskConfig(model="fixed", fixed_size=50_000, max_position_size=10_000)
    size = compute_position_size(config=config, current_equity=100_000, entry_price=1.10, stop_price=None)
    assert size == 10_000


def test_max_position_size_caps_percent_sizing():
    config = RiskConfig(model="percent_of_equity", risk_pct_of_equity=0.5, max_position_size=5_000)
    size = compute_position_size(config=config, current_equity=10_000, entry_price=1.10, stop_price=1.09)
    assert size == 5_000  # would otherwise be 5000/0.01=500,000, capped


def test_invalid_model_rejected():
    with pytest.raises(ValueError):
        RiskConfig(model="leverage_yolo", fixed_size=10)


def test_drawdown_halt_not_configured_returns_false():
    config = RiskConfig(model="fixed", fixed_size=1000)
    assert drawdown_halt_triggered(config=config, current_drawdown_percent=0.99) is False


def test_drawdown_halt_triggers_at_threshold():
    config = RiskConfig(model="fixed", fixed_size=1000, max_drawdown_halt_pct=0.20)
    assert drawdown_halt_triggered(config=config, current_drawdown_percent=0.25) is True
    assert drawdown_halt_triggered(config=config, current_drawdown_percent=0.10) is False


def test_invalid_drawdown_halt_pct_rejected():
    with pytest.raises(ValueError):
        RiskConfig(model="fixed", fixed_size=1000, max_drawdown_halt_pct=1.5)
