import pytest
from datetime import datetime, timezone

from app.paper_trading.account import PaperAccountState
from app.paper_trading.engine import PaperTradingEngine
from app.research.hypothesis import HypothesisType
from app.research.validated_strategy_config import ValidatedStrategyConfig
from app.risk_engine.risk_models import RiskLimitsConfig

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def make_config(**overrides):
    defaults = dict(
        config_id="vsc_test1", candidate_id="cand_test1", instrument="XAU/USD", timeframe="h1",
        strategy_family=HypothesisType.BREAKOUT, parameters={"lookback": 40},
        exit_config_summary={}, cost_assumptions={},
        evidence_period_start="2012-01-01T00:00:00+00:00", evidence_period_end="2022-01-01T00:00:00+00:00",
        gate_status="REJECT_EARLY", verdict="REJECTED", statistical_level="UNKNOWN", regime_evidence={},
    )
    defaults.update(overrides)
    return ValidatedStrategyConfig(**defaults)


def make_engine(configs, equity=10000.0, kill_switch_active=False):
    account = PaperAccountState(account_id="paper-1", initial_equity=equity, kill_switch_active=kill_switch_active)
    return PaperTradingEngine(account=account, configs=configs, risk_limits=RiskLimitsConfig())


def test_scenario_a_fails_research_gate():
    engine = make_engine([make_config(gate_status="REJECT_EARLY", verdict="REJECTED")])
    decision = engine.evaluate_and_maybe_open(
        instrument="XAU/USD", timeframe="h1", direction="LONG",
        entry_price=1900.0, stop_price=1880.0, current_prices={},
    )
    assert decision.status == "NO_VALIDATED_EDGE"
    assert decision.position is None


def test_promising_not_tradeable_never_approved():
    engine = make_engine([make_config(gate_status="PROMISING", verdict="PROMISING", statistical_level="WEAK")])
    decision = engine.evaluate_and_maybe_open(
        instrument="XAU/USD", timeframe="h1", direction="LONG",
        entry_price=1900.0, stop_price=1860.0, current_prices={},
    )
    assert decision.status == "PROMISING_NOT_TRADEABLE"
    assert decision.status != "PAPER_TRADE_APPROVED"
    assert decision.position is None


def test_scenario_b_passes_gate_fails_risk():
    """Candidate passes Research Gate but fails Risk Engine: a stop tight
    enough (relative to entry price) that the resulting risk-based
    position size produces oversized notional exposure -> NO TRADE."""
    engine = make_engine([make_config(gate_status="PAPER_CANDIDATE", verdict="PROMISING")], equity=100000.0)
    decision = engine.evaluate_and_maybe_open(
        instrument="XAU/USD", timeframe="h1", direction="LONG",
        entry_price=1900.0, stop_price=1899.0, current_prices={},  # $1 stop distance on $1,900 gold -> huge notional
    )
    assert decision.status == "RISK_REJECTED"
    assert decision.position is None


def test_scenario_c_full_approval():
    engine = make_engine([make_config(gate_status="PAPER_CANDIDATE", verdict="PROMISING")])
    decision = engine.evaluate_and_maybe_open(
        instrument="XAU/USD", timeframe="h1", direction="LONG",
        entry_price=1900.0, stop_price=1860.0, current_prices={},
    )
    assert decision.status == "PAPER_TRADE_APPROVED"
    assert decision.position is not None
    assert engine.account.get_position("XAU/USD:h1") is not None


def test_kill_switch_blocks_even_approved_candidate():
    engine = make_engine([make_config(gate_status="PAPER_CANDIDATE", verdict="PROMISING")], kill_switch_active=True)
    decision = engine.evaluate_and_maybe_open(
        instrument="XAU/USD", timeframe="h1", direction="LONG",
        entry_price=1900.0, stop_price=1860.0, current_prices={},
    )
    assert decision.status == "KILL_SWITCH_BLOCKED"
    assert decision.position is None


def test_invalid_stop_rejected():
    engine = make_engine([make_config(gate_status="PAPER_CANDIDATE", verdict="PROMISING")])
    decision = engine.evaluate_and_maybe_open(
        instrument="XAU/USD", timeframe="h1", direction="LONG",
        entry_price=1900.0, stop_price=None, current_prices={},
    )
    assert decision.status == "RISK_REJECTED"


def test_research_required_status():
    engine = make_engine([make_config(gate_status="ROBUSTNESS_REQUIRED", verdict="OVERFIT_SUSPECTED")])
    decision = engine.evaluate_and_maybe_open(
        instrument="XAU/USD", timeframe="h1", direction="LONG",
        entry_price=1900.0, stop_price=1860.0, current_prices={},
    )
    assert decision.status == "RESEARCH_REQUIRED"


def test_invalid_timeframe_rejected():
    engine = make_engine([make_config(gate_status="PAPER_CANDIDATE", verdict="PROMISING")])
    decision = engine.evaluate_and_maybe_open(
        instrument="XAU/USD", timeframe="not_a_timeframe", direction="LONG",
        entry_price=1900.0, stop_price=1860.0, current_prices={},
    )
    assert decision.status == "INVALID_INPUT"


def test_duplicate_position_same_instrument_rejected():
    engine = make_engine([make_config(gate_status="PAPER_CANDIDATE", verdict="PROMISING")])
    d1 = engine.evaluate_and_maybe_open(instrument="XAU/USD", timeframe="h1", direction="LONG", entry_price=1900.0, stop_price=1860.0, current_prices={})
    assert d1.status == "PAPER_TRADE_APPROVED"
    d2 = engine.evaluate_and_maybe_open(instrument="XAU/USD", timeframe="h1", direction="LONG", entry_price=1905.0, stop_price=1865.0, current_prices={})
    assert d2.status == "RISK_REJECTED"


def test_multiple_simultaneous_different_instruments_and_timeframes():
    configs = [
        make_config(config_id="vsc_1", instrument="XAU/USD", timeframe="h1", gate_status="PAPER_CANDIDATE", verdict="PROMISING"),
        make_config(config_id="vsc_2", instrument="EUR/USD", timeframe="m15", gate_status="PAPER_CANDIDATE", verdict="PROMISING"),
        make_config(config_id="vsc_3", instrument="GBP/USD", timeframe="h4", gate_status="PAPER_CANDIDATE", verdict="PROMISING"),
    ]
    engine = make_engine(configs, equity=100000.0)
    d1 = engine.evaluate_and_maybe_open(instrument="XAU/USD", timeframe="h1", direction="LONG", entry_price=1900.0, stop_price=1860.0, current_prices={})
    d2 = engine.evaluate_and_maybe_open(instrument="EUR/USD", timeframe="m15", direction="SHORT", entry_price=1.10, stop_price=1.14, current_prices={})
    d3 = engine.evaluate_and_maybe_open(instrument="GBP/USD", timeframe="h4", direction="LONG", entry_price=1.30, stop_price=1.25, current_prices={})
    assert all(d.status == "PAPER_TRADE_APPROVED" for d in (d1, d2, d3))
    assert len(engine.account.open_positions) == 3


def test_tick_closes_position_on_stop_hit():
    engine = make_engine([make_config(gate_status="PAPER_CANDIDATE", verdict="PROMISING")])
    engine.evaluate_and_maybe_open(instrument="XAU/USD", timeframe="h1", direction="LONG", entry_price=1900.0, stop_price=1860.0, current_prices={})
    closed = engine.tick(current_prices={"XAU/USD:h1": 1850.0}, current_time=NOW)
    assert len(closed) == 1
    assert closed[0].exit_reason == "STOP_LOSS"
    assert len(engine.account.open_positions) == 0


def test_tick_closes_position_on_take_profit_hit():
    engine = make_engine([make_config(gate_status="PAPER_CANDIDATE", verdict="PROMISING")])
    engine.evaluate_and_maybe_open(
        instrument="XAU/USD", timeframe="h1", direction="LONG", entry_price=1900.0, stop_price=1860.0,
        take_profit_price=1950.0, current_prices={},
    )
    closed = engine.tick(current_prices={"XAU/USD:h1": 1960.0}, current_time=NOW)
    assert len(closed) == 1
    assert closed[0].exit_reason == "TAKE_PROFIT"


def test_tick_closes_position_on_max_holding_period():
    engine = make_engine([make_config(gate_status="PAPER_CANDIDATE", verdict="PROMISING")])
    engine.evaluate_and_maybe_open(
        instrument="XAU/USD", timeframe="h1", direction="LONG", entry_price=1900.0, stop_price=1860.0,
        max_holding_periods=2, current_prices={},
    )
    closed = engine.tick(current_prices={"XAU/USD:h1": 1900.0}, current_time=NOW)
    assert closed == []
    closed = engine.tick(current_prices={"XAU/USD:h1": 1900.0}, current_time=NOW)
    assert len(closed) == 1
    assert closed[0].exit_reason == "MAX_HOLDING_PERIOD"


def test_tick_leaves_position_open_when_no_exit_condition_met():
    engine = make_engine([make_config(gate_status="PAPER_CANDIDATE", verdict="PROMISING")])
    engine.evaluate_and_maybe_open(instrument="XAU/USD", timeframe="h1", direction="LONG", entry_price=1900.0, stop_price=1860.0, current_prices={})
    closed = engine.tick(current_prices={"XAU/USD:h1": 1905.0}, current_time=NOW)
    assert closed == []
    assert len(engine.account.open_positions) == 1


def test_tick_missing_price_leaves_position_untouched():
    engine = make_engine([make_config(gate_status="PAPER_CANDIDATE", verdict="PROMISING")])
    engine.evaluate_and_maybe_open(instrument="XAU/USD", timeframe="h1", direction="LONG", entry_price=1900.0, stop_price=1860.0, current_prices={})
    closed = engine.tick(current_prices={}, current_time=NOW)
    assert closed == []
    assert len(engine.account.open_positions) == 1


def test_deterministic_decision():
    configs = [make_config(gate_status="PAPER_CANDIDATE", verdict="PROMISING")]
    e1 = make_engine(configs)
    e2 = make_engine(configs)
    d1 = e1.evaluate_and_maybe_open(instrument="XAU/USD", timeframe="h1", direction="LONG", entry_price=1900.0, stop_price=1860.0, current_prices={})
    d2 = e2.evaluate_and_maybe_open(instrument="XAU/USD", timeframe="h1", direction="LONG", entry_price=1900.0, stop_price=1860.0, current_prices={})
    assert d1.status == d2.status


def test_high_macro_event_risk_blocks_trade_before_risk_engine():
    """A candidate that would otherwise be APPROVED must be blocked
    when HIGH macro event risk is supplied -- the safety gate runs
    BEFORE Risk Engine, never after."""
    from app.news_engine.models import MacroEventRisk, MACRO_RISK_HIGH

    engine = make_engine([make_config(gate_status="PAPER_CANDIDATE", verdict="PROMISING")])
    high_risk = MacroEventRisk(level=MACRO_RISK_HIGH, reason="US CPI in 30 minutes.", triggering_events=())

    decision = engine.evaluate_and_maybe_open(
        instrument="XAU/USD", timeframe="h1", direction="LONG", entry_price=1900.0,
        stop_price=1860.0, current_prices={}, macro_event_risk=high_risk,
    )
    assert decision.status == "MACRO_EVENT_RISK_BLOCKED"
    assert decision.status != "PAPER_TRADE_APPROVED"
    assert decision.position is None


def test_low_macro_event_risk_does_not_block_trade():
    from app.news_engine.models import MacroEventRisk, MACRO_RISK_LOW

    engine = make_engine([make_config(gate_status="PAPER_CANDIDATE", verdict="PROMISING")])
    low_risk = MacroEventRisk(level=MACRO_RISK_LOW, reason="No relevant events soon.", triggering_events=())

    decision = engine.evaluate_and_maybe_open(
        instrument="XAU/USD", timeframe="h1", direction="LONG", entry_price=1900.0,
        stop_price=1860.0, current_prices={}, macro_event_risk=low_risk,
    )
    assert decision.status == "PAPER_TRADE_APPROVED"


def test_omitted_macro_event_risk_does_not_change_prior_behavior():
    """Backward compatibility: every existing caller that doesn't pass
    macro_event_risk at all must behave exactly as before."""
    engine = make_engine([make_config(gate_status="PAPER_CANDIDATE", verdict="PROMISING")])

    decision = engine.evaluate_and_maybe_open(
        instrument="XAU/USD", timeframe="h1", direction="LONG", entry_price=1900.0,
        stop_price=1860.0, current_prices={},
    )
    assert decision.status == "PAPER_TRADE_APPROVED"
