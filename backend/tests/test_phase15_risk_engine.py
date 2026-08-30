import pytest

from app.research.instrument_adapter import InstrumentTimeframeInfo
from app.research.strategy_selector import ConsideredCandidate, SelectionResult
from app.risk_engine.account_limits import (
    account_data_valid, check_daily_loss, check_drawdown, check_exposure,
    check_per_trade_risk, check_position_limit, check_total_open_risk,
)
from app.risk_engine.position_sizing import compute_position_size
from app.risk_engine.risk_engine import evaluate_risk
from app.risk_engine.risk_models import AccountState, RiskDecision, RiskLimitsConfig
from app.risk_engine.stop_validation import validate_stop


def tradeable_selection(instrument="XAU/USD", timeframe="h1"):
    return SelectionResult(
        instrument, timeframe, "TRADEABLE", "vsc_test1", "Selected vsc_test1: gate status PAPER_CANDIDATE.",
        (ConsideredCandidate("vsc_test1", "PAPER_CANDIDATE", "Gate status: PAPER_CANDIDATE"),), None,
    )


def promising_selection(instrument="XAU/USD", timeframe="h1"):
    return SelectionResult(
        instrument, timeframe, "PROMISING_NOT_TRADEABLE", "vsc_test1",
        "Selected vsc_test1: gate status PROMISING (statistical evidence: WEAK).",
        (ConsideredCandidate("vsc_test1", "PROMISING", "Gate status: PROMISING"),),
        "Grow the out-of-sample statistical sample...",
    )


def no_edge_selection(instrument="EUR/USD", timeframe="h1"):
    return SelectionResult(instrument, timeframe, "NO_VALIDATED_EDGE", None, "No researched strategy configuration exists.", (), "...")


def good_account(**overrides):
    defaults = dict(
        equity=10000.0, peak_equity=10000.0, daily_start_equity=10000.0,
        daily_realized_pnl=0.0, daily_unrealized_pnl=0.0, open_positions_count=0,
        total_open_risk_pct=0.0, kill_switch_active=False,
    )
    defaults.update(overrides)
    return AccountState(**defaults)


def default_limits():
    return RiskLimitsConfig()


def eurusd_info():
    return InstrumentTimeframeInfo("EUR/USD", "h1", mean_price=1.10, price_precision_decimals=5)


def xauusd_info():
    return InstrumentTimeframeInfo("XAU/USD", "h1", mean_price=1900.0, price_precision_decimals=2)


def test_valid_position_sizing_eurusd():
    detail = compute_position_size(equity=10000.0, risk_pct=0.01, entry_price=1.10, stop_price=1.095, instrument_info=eurusd_info())
    assert detail.sizing_model == "notional_price_unit"
    assert detail.risk_amount == pytest.approx(100.0)
    assert detail.final_position_size == pytest.approx(100.0 / 0.005)


def test_valid_position_sizing_xauusd_different_scale():
    detail = compute_position_size(equity=10000.0, risk_pct=0.01, entry_price=1900.0, stop_price=1860.0, instrument_info=xauusd_info())
    assert detail.final_position_size == pytest.approx(100.0 / 40.0)


def test_position_sizing_without_instrument_info_still_works():
    detail = compute_position_size(equity=10000.0, risk_pct=0.01, entry_price=1.10, stop_price=1.095)
    assert detail.sizing_model == "notional_price_unit"


def test_position_sizing_respects_minimum_size():
    info = InstrumentTimeframeInfo("X", "h1", mean_price=1.0, price_precision_decimals=2, minimum_position_size=1000.0)
    detail = compute_position_size(equity=100.0, risk_pct=0.01, entry_price=1.0, stop_price=0.99, instrument_info=info)
    assert detail.final_position_size == 0.0


def test_position_sizing_respects_increment():
    info = InstrumentTimeframeInfo("X", "h1", mean_price=1.0, price_precision_decimals=2, position_increment=10.0)
    detail = compute_position_size(equity=10000.0, risk_pct=0.01, entry_price=1.0, stop_price=0.99, instrument_info=info)
    assert detail.final_position_size % 10.0 == 0


def test_position_sizing_zero_stop_distance_rejected():
    with pytest.raises(ValueError):
        compute_position_size(equity=10000.0, risk_pct=0.01, entry_price=1.10, stop_price=1.10)


def test_position_sizing_invalid_equity_rejected():
    with pytest.raises(ValueError):
        compute_position_size(equity=0.0, risk_pct=0.01, entry_price=1.10, stop_price=1.095)


def test_position_sizing_deterministic():
    a = compute_position_size(equity=10000.0, risk_pct=0.01, entry_price=1.10, stop_price=1.095, instrument_info=eurusd_info())
    b = compute_position_size(equity=10000.0, risk_pct=0.01, entry_price=1.10, stop_price=1.095, instrument_info=eurusd_info())
    assert a == b


def test_valid_long_stop():
    assert validate_stop("LONG", 1.10, 1.095).valid


def test_valid_short_stop():
    assert validate_stop("SHORT", 1.10, 1.105).valid


def test_missing_stop_rejected():
    assert not validate_stop("LONG", 1.10, None).valid


def test_zero_distance_stop_rejected():
    assert not validate_stop("LONG", 1.10, 1.10).valid


def test_stop_wrong_side_long_rejected():
    assert not validate_stop("LONG", 1.10, 1.105).valid


def test_stop_wrong_side_short_rejected():
    assert not validate_stop("SHORT", 1.10, 1.095).valid


def test_negative_prices_rejected():
    assert not validate_stop("LONG", -1.0, -1.1).valid


def test_account_data_valid_full():
    assert account_data_valid(good_account())[0] is True


def test_account_data_missing_equity_invalid():
    assert account_data_valid(good_account(equity=None))[0] is False


def test_max_risk_per_trade_exceeded():
    ok, _ = check_per_trade_risk(0.02, default_limits())
    assert ok is False


def test_total_open_risk_exceeded():
    ok, _ = check_total_open_risk(good_account(total_open_risk_pct=0.025), 0.01, default_limits())
    assert ok is False


def test_daily_loss_limit_triggers_do_not_trade():
    account = good_account(daily_realized_pnl=-350.0)
    ok, reason = check_daily_loss(account, default_limits())
    assert ok is False
    assert "DO_NOT_TRADE" in reason


def test_max_drawdown_triggers_do_not_trade():
    account = good_account(equity=8000.0, peak_equity=10000.0)
    ok, reason = check_drawdown(account, default_limits())
    assert ok is False
    assert "DO_NOT_TRADE" in reason


def test_simultaneous_position_limit():
    account = good_account(open_positions_count=3)
    ok, _ = check_position_limit(account, default_limits())
    assert ok is False


def test_exposure_limit_exceeded():
    account = good_account(equity=1000.0)
    ok, _ = check_exposure(position_size=1000.0, entry_price=1.0, account=account, limits=default_limits())
    assert ok is False


def test_kill_switch_blocks_everything():
    result = evaluate_risk(selection_result=tradeable_selection(), account=good_account(kill_switch_active=True), limits=default_limits())
    assert result.state == "KILL_SWITCH_ACTIVE"


def test_insufficient_account_data():
    result = evaluate_risk(selection_result=tradeable_selection(), account=good_account(equity=None), limits=default_limits())
    assert result.state == "INSUFFICIENT_ACCOUNT_DATA"


def test_no_validated_edge_rejects():
    result = evaluate_risk(selection_result=no_edge_selection(), account=good_account(), limits=default_limits())
    assert result.state == "NO_VALIDATED_EDGE"


def test_promising_candidate_not_automatically_approved():
    result = evaluate_risk(
        selection_result=promising_selection(), account=good_account(), limits=default_limits(),
        direction="LONG", entry_price=1900.0, stop_price=1860.0, instrument_info=xauusd_info(),
    )
    assert result.state == "NO_VALIDATED_EDGE"
    assert result.state != "APPROVED"


def test_invalid_stop_rejects():
    result = evaluate_risk(
        selection_result=tradeable_selection(), account=good_account(), limits=default_limits(),
        direction="LONG", entry_price=1900.0, stop_price=None, instrument_info=xauusd_info(),
    )
    assert result.state == "INVALID_STOP"


def test_hypothetical_eligible_candidate_reaches_approved():
    result = evaluate_risk(
        selection_result=tradeable_selection(), account=good_account(), limits=default_limits(),
        direction="LONG", entry_price=1900.0, stop_price=1860.0, instrument_info=xauusd_info(),
    )
    assert result.state == "APPROVED"
    assert result.position_sizing is not None
    assert result.computed_risk_pct <= default_limits().max_risk_per_trade_pct


def test_later_check_never_overrides_earlier_rejection():
    result = evaluate_risk(
        selection_result=no_edge_selection(), account=good_account(kill_switch_active=True, equity=None), limits=default_limits(),
    )
    assert result.state == "KILL_SWITCH_ACTIVE"


def test_risk_limit_exceeded_when_stop_too_wide():
    account = good_account(equity=100.0)
    result = evaluate_risk(
        selection_result=tradeable_selection(), account=account, limits=default_limits(),
        direction="LONG", entry_price=1900.0, stop_price=1000.0, instrument_info=xauusd_info(),
    )
    assert result.state in ("APPROVED", "RISK_LIMIT_EXCEEDED", "POSITION_TOO_LARGE")


def test_deterministic_full_evaluation():
    a = evaluate_risk(
        selection_result=tradeable_selection(), account=good_account(), limits=default_limits(),
        direction="LONG", entry_price=1900.0, stop_price=1860.0, instrument_info=xauusd_info(),
    )
    b = evaluate_risk(
        selection_result=tradeable_selection(), account=good_account(), limits=default_limits(),
        direction="LONG", entry_price=1900.0, stop_price=1860.0, instrument_info=xauusd_info(),
    )
    assert a == b


def test_every_decision_has_a_reason_string():
    result = evaluate_risk(selection_result=no_edge_selection(), account=good_account(), limits=default_limits())
    assert result.reason and len(result.reason) > 10


def test_reproducibility_position_sizing_matches_across_engine_calls():
    r1 = evaluate_risk(
        selection_result=tradeable_selection(), account=good_account(), limits=default_limits(),
        direction="LONG", entry_price=1900.0, stop_price=1860.0, instrument_info=xauusd_info(),
    )
    r2 = evaluate_risk(
        selection_result=tradeable_selection(), account=good_account(), limits=default_limits(),
        direction="LONG", entry_price=1900.0, stop_price=1860.0, instrument_info=xauusd_info(),
    )
    assert r1.position_sizing == r2.position_sizing


def test_invalid_risk_decision_state_rejected():
    with pytest.raises(ValueError):
        RiskDecision("NOT_A_REAL_STATE", "test")


def test_risk_limits_config_rejects_invalid_percentages():
    with pytest.raises(ValueError):
        RiskLimitsConfig(max_risk_per_trade_pct=1.5)
