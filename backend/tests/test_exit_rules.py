import pytest

from app.backtesting.exit_rules import ExitConfig, compute_stop_target_prices


def test_fixed_pct_stop_long():
    stop, target = compute_stop_target_prices(
        direction="LONG", entry_price=1.1000, entry_atr_14=None,
        exit_config=ExitConfig(label="t", stop_loss_pct=0.01),
    )
    assert stop == pytest.approx(1.1000 - 0.011)
    assert target is None


def test_fixed_pct_stop_short():
    stop, target = compute_stop_target_prices(
        direction="SHORT", entry_price=1.1000, entry_atr_14=None,
        exit_config=ExitConfig(label="t", stop_loss_pct=0.01),
    )
    assert stop == pytest.approx(1.1000 + 0.011)


def test_fixed_pct_take_profit_long():
    stop, target = compute_stop_target_prices(
        direction="LONG", entry_price=1.1000, entry_atr_14=None,
        exit_config=ExitConfig(label="t", take_profit_pct=0.02),
    )
    assert target == pytest.approx(1.1000 + 0.022)
    assert stop is None


def test_atr_stop_long():
    stop, target = compute_stop_target_prices(
        direction="LONG", entry_price=1.1000, entry_atr_14=0.0010,
        exit_config=ExitConfig(label="t", atr_stop_multiple=2.0),
    )
    assert stop == pytest.approx(1.1000 - 0.0020)


def test_atr_stop_requires_atr_value():
    with pytest.raises(ValueError, match="ATR"):
        compute_stop_target_prices(
            direction="LONG", entry_price=1.1000, entry_atr_14=None,
            exit_config=ExitConfig(label="t", atr_stop_multiple=2.0),
        )


def test_cannot_combine_pct_and_atr_stop():
    with pytest.raises(ValueError, match="one stop mechanism"):
        ExitConfig(label="t", stop_loss_pct=0.01, atr_stop_multiple=2.0)


def test_cannot_combine_pct_and_atr_target():
    with pytest.raises(ValueError, match="one target mechanism"):
        ExitConfig(label="t", take_profit_pct=0.02, atr_take_profit_multiple=2.0)


def test_rejects_non_positive_values():
    with pytest.raises(ValueError):
        ExitConfig(label="t", stop_loss_pct=0.0)
    with pytest.raises(ValueError):
        ExitConfig(label="t", max_holding_candles=0)


def test_no_mechanism_returns_none_none():
    stop, target = compute_stop_target_prices(
        direction="LONG", entry_price=1.1000, entry_atr_14=None,
        exit_config=ExitConfig(label="baseline"),
    )
    assert stop is None and target is None
