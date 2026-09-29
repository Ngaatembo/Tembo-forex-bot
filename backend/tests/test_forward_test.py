"""Owner-approved forward testing of PROMISING strategies (paper / Deriv demo only)."""

import pytest

from app.paper_trading.account import PaperAccountState
from app.paper_trading.engine import PaperTradingEngine
from app.research.forward_test import (
    FORWARD_TEST_MAX_RISK_PER_TRADE,
    forward_test_config_ids,
    forward_test_limits,
    is_forward_test,
)
from app.risk_engine.risk_models import RiskLimitsConfig
from tests.test_paper_trading_engine import make_config

PROMISING = dict(config_id="vsc_gold", gate_status="PROMISING", verdict="PROMISING", statistical_level="WEAK")


def _engine(configs, allowed=frozenset()):
    account = PaperAccountState(account_id="paper-1", initial_equity=10000.0)
    return PaperTradingEngine(account=account, configs=configs, risk_limits=RiskLimitsConfig(), forward_test_config_ids=allowed)


def _open(engine):
    return engine.evaluate_and_maybe_open(
        instrument="XAU/USD", timeframe="h1", direction="LONG",
        entry_price=1900.0, stop_price=1860.0, current_prices={},
    )


def test_promising_stays_blocked_without_explicit_allowlist():
    decision = _open(_engine([make_config(**PROMISING)]))
    assert decision.status == "PROMISING_NOT_TRADEABLE"
    assert decision.position is None


def test_promising_blocked_when_a_different_config_is_allowlisted():
    decision = _open(_engine([make_config(**PROMISING)], allowed=frozenset({"vsc_other"})))
    assert decision.status == "PROMISING_NOT_TRADEABLE"
    assert decision.position is None


def test_allowlisted_promising_config_opens_a_forward_test_position():
    engine = _engine([make_config(**PROMISING)], allowed=frozenset({"vsc_gold"}))
    decision = _open(engine)
    assert decision.status == "FORWARD_TEST_APPROVED"
    assert decision.position is not None
    assert decision.position.candidate_config_id == "vsc_gold"


def test_forward_test_uses_half_risk():
    normal = _open(_engine([make_config(config_id="vsc_gold", gate_status="PAPER_CANDIDATE", verdict="PROMISING")]))
    forward = _open(_engine([make_config(**PROMISING)], allowed=frozenset({"vsc_gold"})))
    assert normal.status == "PAPER_TRADE_APPROVED"
    assert forward.position.position_size == pytest.approx(normal.position.position_size / 2)


def test_forward_test_never_unlocks_rejected_configs():
    rejected = make_config(config_id="vsc_gold", gate_status="REJECT_EARLY", verdict="REJECTED")
    decision = _open(_engine([rejected], allowed=frozenset({"vsc_gold"})))
    assert decision.status == "NO_VALIDATED_EDGE"
    assert decision.position is None


def test_kill_switch_still_blocks_forward_test():
    account = PaperAccountState(account_id="paper-1", initial_equity=10000.0, kill_switch_active=True)
    engine = PaperTradingEngine(account=account, configs=[make_config(**PROMISING)], risk_limits=RiskLimitsConfig(), forward_test_config_ids=frozenset({"vsc_gold"}))
    decision = _open(engine)
    assert decision.position is None


def test_is_forward_test_only_for_promising_status():
    allowed = frozenset({"vsc_gold"})
    assert is_forward_test("PROMISING_NOT_TRADEABLE", "vsc_gold", allowed)
    assert not is_forward_test("NO_VALIDATED_EDGE", "vsc_gold", allowed)
    assert not is_forward_test("RESEARCH_REQUIRED", "vsc_gold", allowed)
    assert not is_forward_test("PROMISING_NOT_TRADEABLE", None, allowed)


def test_forward_test_limits_cap_per_trade_risk():
    assert forward_test_limits(RiskLimitsConfig()).max_risk_per_trade_pct == FORWARD_TEST_MAX_RISK_PER_TRADE
    assert forward_test_limits(RiskLimitsConfig(max_risk_per_trade_pct=0.002)).max_risk_per_trade_pct == 0.002


@pytest.mark.parametrize("raw,expected", [
    ("vsc_a, vsc_b", {"vsc_a", "vsc_b"}),
    ("", set()),
    ("none", set()),
    (" None ", set()),
])
def test_allowlist_parsing(monkeypatch, raw, expected):
    from app.core.config import get_settings
    monkeypatch.setenv("DEMO_FORWARD_TEST_CONFIGS", raw)
    get_settings.cache_clear()
    try:
        assert forward_test_config_ids() == frozenset(expected)
    finally:
        get_settings.cache_clear()


@pytest.mark.parametrize("value", ["demo", "Demo", " demo ", '"demo"', "'demo'"])
def test_deriv_mode_tolerates_whitespace_and_quotes(monkeypatch, value):
    from app.core.config import get_settings
    from app.integrations.deriv import DerivDemoClient
    monkeypatch.setenv("DERIV_TRADING_MODE", value)
    monkeypatch.setenv("DERIV_API_TOKEN", " tok ")
    monkeypatch.setenv("DERIV_ACCOUNT_ID", " acc ")
    get_settings.cache_clear()
    try:
        client = DerivDemoClient()
        assert client.mode == "demo"
        assert client.token == "tok" and client.account_id == "acc"
    finally:
        get_settings.cache_clear()


@pytest.mark.parametrize("value", ["real", "live", "DERIV_TRADING_MODE=demo"])
def test_deriv_mode_still_refuses_anything_but_demo(monkeypatch, value):
    from app.core.config import get_settings
    from app.integrations.deriv import DerivConfigurationError, DerivDemoClient
    monkeypatch.setenv("DERIV_TRADING_MODE", value)
    monkeypatch.setenv("DERIV_API_TOKEN", "tok")
    monkeypatch.setenv("DERIV_ACCOUNT_ID", "acc")
    get_settings.cache_clear()
    try:
        with pytest.raises(DerivConfigurationError) as exc:
            DerivDemoClient()
        assert repr(value) in str(exc.value)
    finally:
        get_settings.cache_clear()


def test_forward_test_allows_up_to_3x_leverage_but_not_more():
    from app.research.forward_test import FORWARD_TEST_MAX_EXPOSURE

    assert FORWARD_TEST_MAX_EXPOSURE == 3.0
    assert forward_test_limits(RiskLimitsConfig()).max_exposure_pct == 3.0
    assert RiskLimitsConfig(max_exposure_pct=3.0).max_exposure_pct == 3.0
    with pytest.raises(ValueError):
        RiskLimitsConfig(max_exposure_pct=11.0)
    with pytest.raises(ValueError):
        RiskLimitsConfig(max_exposure_pct=0.0)
    # Everything else keeps its (0, 1] bound.
    with pytest.raises(ValueError):
        RiskLimitsConfig(max_risk_per_trade_pct=1.5)


@pytest.mark.parametrize("instrument,entry,stop", [
    ("USD/JPY", 149.50, 149.20),
    ("EUR/USD", 1.1370, 1.1350),
])
def test_typical_forex_forward_test_trade_is_approved_only_with_forward_test_limits(instrument, entry, stop):
    from app.research.instrument_adapter import InstrumentTimeframeInfo
    from app.research.strategy_selector import SelectionResult
    from app.risk_engine.risk_engine import evaluate_risk
    from app.risk_engine.risk_models import AccountState

    selection = SelectionResult(instrument, "h1", "PROMISING_NOT_TRADEABLE", "cfg", "r", (), None)
    account = AccountState(
        equity=10000.0, peak_equity=10000.0, daily_start_equity=10000.0, daily_realized_pnl=0.0,
        daily_unrealized_pnl=0.0, open_positions_count=0, total_open_risk_pct=0.0, kill_switch_active=False,
    )
    info = InstrumentTimeframeInfo(instrument, "h1", mean_price=entry, price_precision_decimals=5)
    kwargs = dict(selection_result=selection, account=account, direction="LONG", entry_price=entry, stop_price=stop, instrument_info=info)

    default = evaluate_risk(limits=RiskLimitsConfig(), forward_test=True, **kwargs)
    assert default.state == "RISK_LIMIT_EXCEEDED" and default.hierarchy_stage == "exposure"

    forward = evaluate_risk(limits=forward_test_limits(RiskLimitsConfig()), forward_test=True, **kwargs)
    assert forward.state == "APPROVED"
    assert forward.computed_risk_pct == pytest.approx(0.005)


def test_usdjpy_h1_breakout_is_the_default_forward_test():
    import json
    from pathlib import Path

    from app.core.config import Settings

    assert Settings().demo_forward_test_configs == "vsc_exp4_usdjpy_h1_breakout_55"
    registry = json.loads((Path(__file__).resolve().parents[2] / "research" / "results" / "validated_strategy_configs.json").read_text())
    cfg = next(c for c in registry if c["config_id"] == "vsc_exp4_usdjpy_h1_breakout_55")
    assert (cfg["instrument"], cfg["timeframe"], cfg["strategy_family"], cfg["gate_status"]) == ("USD/JPY", "h1", "breakout", "PROMISING")
    assert cfg["exit_config_summary"]["atr_stop_multiple"] == 2.0
