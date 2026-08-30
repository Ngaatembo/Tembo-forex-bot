"""
Risk Engine — the main orchestrator. Implements the exact safety
hierarchy from the Phase 15 spec, sequentially, with an immediate
return on the first failure. A later stage can NEVER override an
earlier rejection — this is enforced structurally (each stage is a
separate early-return, not a scored/weighted combination).

    KILL SWITCH
      -> ACCOUNT DATA VALID?
      -> VALIDATED STRATEGY? (Phase 14's Selector)
      -> INSTRUMENT DATA VALID?
      -> STOP VALID?
      -> PER-TRADE RISK
      -> TOTAL OPEN RISK
      -> DAILY LOSS
      -> DRAWDOWN
      -> POSITION LIMIT
      -> EXPOSURE LIMIT
      -> APPROVED

SECURITY: this module has no import of, and no code path to, the
execution/broker layer. It produces a RiskDecision — a piece of
data — never places anything. See test_risk_engine_security_boundary.py.

"PROMISING" != tradeable: a candidate whose Strategy Selector status
is anything other than "TRADEABLE" (i.e. it never reached gate status
PAPER_CANDIDATE) is rejected at the "VALIDATED STRATEGY?" stage,
before any risk/position-sizing calculation even happens. This is
what makes it structurally impossible for XAU/USD Breakout's current
PROMISING status to reach APPROVED.
"""

from typing import Optional

from app.research.instrument_adapter import InstrumentTimeframeInfo
from app.research.strategy_selector import SelectionResult
from app.risk_engine.account_limits import (
    account_data_valid, check_daily_loss, check_drawdown, check_exposure,
    check_per_trade_risk, check_position_limit, check_total_open_risk,
)
from app.risk_engine.position_sizing import compute_position_size
from app.risk_engine.risk_models import AccountState, RiskDecision, RiskLimitsConfig
from app.risk_engine.stop_validation import validate_stop


def evaluate_risk(
    *,
    selection_result: SelectionResult,
    account: AccountState,
    limits: RiskLimitsConfig,
    direction: Optional[str] = None,
    entry_price: Optional[float] = None,
    stop_price: Optional[float] = None,
    instrument_info: Optional[InstrumentTimeframeInfo] = None,
) -> RiskDecision:
    if account.kill_switch_active:
        return RiskDecision("KILL_SWITCH_ACTIVE", "Account-level kill switch is active — no trading permitted.", hierarchy_stage="kill_switch")

    valid, reason = account_data_valid(account)
    if not valid:
        return RiskDecision("INSUFFICIENT_ACCOUNT_DATA", reason, hierarchy_stage="account_data")

    if selection_result.status != "TRADEABLE":
        return RiskDecision(
            "NO_VALIDATED_EDGE",
            f"Strategy Selector returned status '{selection_result.status}' for "
            f"{selection_result.instrument} {selection_result.timeframe}, not TRADEABLE. {selection_result.reason}",
            hierarchy_stage="validated_strategy",
        )

    if instrument_info is None or entry_price is None or direction is None:
        return RiskDecision("INVALID_INSTRUMENT", "Missing instrument metadata, entry price, or direction.", hierarchy_stage="instrument_data")
    if entry_price <= 0:
        return RiskDecision("INVALID_INSTRUMENT", f"Entry price must be positive, got {entry_price}.", hierarchy_stage="instrument_data")

    stop_result = validate_stop(direction, entry_price, stop_price)
    if not stop_result.valid:
        return RiskDecision("INVALID_STOP", stop_result.reason, hierarchy_stage="stop_valid")

    try:
        sizing = compute_position_size(
            equity=account.equity, risk_pct=limits.max_risk_per_trade_pct,
            entry_price=entry_price, stop_price=stop_price, instrument_info=instrument_info,
        )
    except ValueError as e:
        return RiskDecision("INVALID_STOP", f"Position sizing failed: {e}", hierarchy_stage="position_sizing")

    if sizing.final_position_size <= 0:
        return RiskDecision(
            "POSITION_TOO_LARGE",
            f"Calculated position size rounds to zero given instrument constraints ({sizing.notes})",
            position_sizing=sizing, hierarchy_stage="position_sizing",
        )

    actual_risk_amount = sizing.final_position_size * sizing.stop_distance
    computed_risk_pct = actual_risk_amount / account.equity

    ok, reason = check_per_trade_risk(computed_risk_pct, limits)
    if not ok:
        return RiskDecision("RISK_LIMIT_EXCEEDED", reason, position_sizing=sizing, computed_risk_pct=computed_risk_pct, hierarchy_stage="per_trade_risk")

    ok, reason = check_total_open_risk(account, computed_risk_pct, limits)
    if not ok:
        return RiskDecision("RISK_LIMIT_EXCEEDED", reason, position_sizing=sizing, computed_risk_pct=computed_risk_pct, hierarchy_stage="total_open_risk")

    ok, reason = check_daily_loss(account, limits)
    if not ok:
        return RiskDecision("RISK_LIMIT_EXCEEDED", reason, position_sizing=sizing, computed_risk_pct=computed_risk_pct, hierarchy_stage="daily_loss")

    ok, reason = check_drawdown(account, limits)
    if not ok:
        return RiskDecision("RISK_LIMIT_EXCEEDED", reason, position_sizing=sizing, computed_risk_pct=computed_risk_pct, hierarchy_stage="drawdown")

    ok, reason = check_position_limit(account, limits)
    if not ok:
        return RiskDecision("RISK_LIMIT_EXCEEDED", reason, position_sizing=sizing, computed_risk_pct=computed_risk_pct, hierarchy_stage="position_limit")

    ok, reason = check_exposure(sizing.final_position_size, entry_price, account, limits)
    if not ok:
        return RiskDecision("RISK_LIMIT_EXCEEDED", reason, position_sizing=sizing, computed_risk_pct=computed_risk_pct, hierarchy_stage="exposure")

    return RiskDecision(
        "APPROVED",
        f"Candidate is eligible, stop is valid, calculated risk is {computed_risk_pct:.2%}, "
        f"total open risk remains within account limits.",
        position_sizing=sizing, computed_risk_pct=computed_risk_pct, hierarchy_stage="approved",
    )
