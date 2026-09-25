"""
Deterministic, synthetic validation of the paper-trading safety chain.

This suite never touches a broker, never reads live market data, and
never mutates a persistent account. It exercises the same
Strategy Selector -> Research Gate -> Macro Safety -> Risk Engine ->
Paper Position lifecycle used by paper trading.

The results are diagnostic evidence, not trading performance.
"""

from datetime import datetime, timezone

from app.news_engine.models import MACRO_RISK_HIGH, MACRO_RISK_LOW, MacroEventRisk
from app.paper_trading.account import PaperAccountState
from app.paper_trading.engine import PaperTradingEngine
from app.research.hypothesis import HypothesisType
from app.research.validated_strategy_config import ValidatedStrategyConfig
from app.risk_engine.risk_models import RiskLimitsConfig


def _config(
    *,
    config_id: str = "paper_validation",
    instrument: str = "XAU/USD",
    timeframe: str = "h1",
    gate_status: str = "PAPER_CANDIDATE",
    verdict: str = "PROMISING",
) -> ValidatedStrategyConfig:
    return ValidatedStrategyConfig(
        config_id=config_id,
        candidate_id=f"{config_id}_candidate",
        instrument=instrument,
        timeframe=timeframe,
        strategy_family=HypothesisType.BREAKOUT,
        parameters={"lookback": 40},
        exit_config_summary={},
        cost_assumptions={},
        evidence_period_start="2012-01-01T00:00:00+00:00",
        evidence_period_end="2022-01-01T00:00:00+00:00",
        gate_status=gate_status,
        verdict=verdict,
        statistical_level="WEAK" if verdict == "PROMISING" else "UNKNOWN",
        regime_evidence={},
    )


def _engine(*configs: ValidatedStrategyConfig, equity: float = 10_000.0, kill_switch_active: bool = False) -> PaperTradingEngine:
    account = PaperAccountState(
        account_id="paper-validation",
        initial_equity=equity,
        kill_switch_active=kill_switch_active,
    )
    return PaperTradingEngine(
        account=account,
        configs=list(configs),
        risk_limits=RiskLimitsConfig(),
    )


def _check(name: str, expected: str, actual: str, passed: bool, detail: str) -> dict:
    return {
        "name": name,
        "expected": expected,
        "actual": actual,
        "passed": passed,
        "detail": detail,
    }


def run_paper_validation_suite() -> dict:
    checks: list[dict] = []

    rejected = _engine(_config(gate_status="REJECT_EARLY", verdict="REJECTED"))
    decision = rejected.evaluate_and_maybe_open(
        instrument="XAU/USD",
        timeframe="h1",
        direction="LONG",
        entry_price=1900.0,
        stop_price=1860.0,
        current_prices={},
    )
    checks.append(
        _check(
            "research_gate_blocks_rejected_candidate",
            "NO_VALIDATED_EDGE",
            decision.status,
            decision.status == "NO_VALIDATED_EDGE" and decision.position is None,
            decision.reason,
        )
    )

    promising = _engine(_config(gate_status="PROMISING", verdict="PROMISING"))
    decision = promising.evaluate_and_maybe_open(
        instrument="XAU/USD",
        timeframe="h1",
        direction="LONG",
        entry_price=1900.0,
        stop_price=1860.0,
        current_prices={},
    )
    checks.append(
        _check(
            "promising_candidate_cannot_become_trade",
            "PROMISING_NOT_TRADEABLE",
            decision.status,
            decision.status == "PROMISING_NOT_TRADEABLE" and decision.position is None,
            decision.reason,
        )
    )

    macro_blocked = _engine(_config())
    decision = macro_blocked.evaluate_and_maybe_open(
        instrument="XAU/USD",
        timeframe="h1",
        direction="LONG",
        entry_price=1900.0,
        stop_price=1860.0,
        current_prices={},
        macro_event_risk=MacroEventRisk(
            level=MACRO_RISK_HIGH,
            reason="Synthetic high-impact event for validation.",
            triggering_events=(),
        ),
    )
    checks.append(
        _check(
            "high_macro_risk_blocks_before_risk_engine",
            "MACRO_EVENT_RISK_BLOCKED",
            decision.status,
            decision.status == "MACRO_EVENT_RISK_BLOCKED" and decision.position is None,
            decision.reason,
        )
    )

    low_macro = _engine(_config())
    decision = low_macro.evaluate_and_maybe_open(
        instrument="XAU/USD",
        timeframe="h1",
        direction="LONG",
        entry_price=1900.0,
        stop_price=1860.0,
        current_prices={},
        macro_event_risk=MacroEventRisk(
            level=MACRO_RISK_LOW,
            reason="Synthetic low-risk calendar state.",
            triggering_events=(),
        ),
    )
    checks.append(
        _check(
            "low_macro_risk_preserves_risk_gate",
            "PAPER_TRADE_APPROVED",
            decision.status,
            decision.status == "PAPER_TRADE_APPROVED" and decision.position is not None,
            decision.reason,
        )
    )

    killed = _engine(_config(), kill_switch_active=True)
    decision = killed.evaluate_and_maybe_open(
        instrument="XAU/USD",
        timeframe="h1",
        direction="LONG",
        entry_price=1900.0,
        stop_price=1860.0,
        current_prices={},
    )
    checks.append(
        _check(
            "kill_switch_blocks_candidate",
            "KILL_SWITCH_BLOCKED",
            decision.status,
            decision.status == "KILL_SWITCH_BLOCKED" and decision.position is None,
            decision.reason,
        )
    )

    lifecycle = _engine(_config())
    opened = lifecycle.evaluate_and_maybe_open(
        instrument="XAU/USD",
        timeframe="h1",
        direction="LONG",
        entry_price=1900.0,
        stop_price=1860.0,
        current_prices={},
    )
    closed = (
        lifecycle.tick(
            current_prices={"XAU/USD:h1": 1850.0},
            current_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        if opened.position is not None
        else []
    )
    passed = (
        opened.status == "PAPER_TRADE_APPROVED"
        and len(closed) == 1
        and closed[0].exit_reason == "STOP_LOSS"
        and closed[0].realized_pnl < 0
        and not lifecycle.account.open_positions
    )
    checks.append(
        _check(
            "paper_position_stop_lifecycle",
            "OPEN_THEN_STOP_LOSS_CLOSE",
            "OPEN_THEN_STOP_LOSS_CLOSE" if passed else "LIFECYCLE_FAILED",
            passed,
            f"opened={opened.status}; closed={len(closed)}",
        )
    )

    return {
        "suite": "paper-trading-safety-v1",
        "status": "PASS" if all(check["passed"] for check in checks) else "FAIL",
        "synthetic": True,
        "persistent_state_changed": False,
        "real_broker_contacted": False,
        "execution_enabled": False,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "note": "Synthetic safety validation only. A PASS confirms software-path behavior, not profitability or live-trading safety.",
    }
