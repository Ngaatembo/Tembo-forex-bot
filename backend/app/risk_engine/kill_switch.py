"""
Emergency kill switch and risk-state gate.

Rule from the project spec: "If risk state is unknown, DO NOT TRADE."
This module is the single choke point every future order-placing code
path must call through. It fails closed by design — any exception or
unknown state returns "blocked", never "allowed".

Position sizing, daily/weekly loss limits, and drawdown tracking are
implemented in later phases (they need real trade history to compute
against); this file establishes the fail-closed contract they'll all
plug into.
"""

from dataclasses import dataclass
from enum import Enum


class RiskState(str, Enum):
    OK = "ok"
    BLOCKED = "blocked"
    UNKNOWN = "unknown"


@dataclass
class RiskCheckResult:
    state: RiskState
    reason: str

    @property
    def allowed(self) -> bool:
        return self.state == RiskState.OK


def check_kill_switch(*, kill_switch_active: bool, manually_triggered: bool = False) -> RiskCheckResult:
    """
    Real implementation (replaces the Phase 0 placeholder, which
    always returned BLOCKED because no trading logic existed yet to
    safely allow OK). Still fails closed: `kill_switch_active` has no
    default — the caller must be explicit about the actual configured
    state, never accidentally "safe by omission."

    NOTE ON A GAP THIS FIXES: Phase 15's app.risk_engine.evaluate_risk()
    independently checks AccountState.kill_switch_active as its own
    first hierarchy stage — that check was never actually calling this
    function, leaving two disconnected kill-switch concepts in the
    codebase. app.paper_trading.engine.PaperTradingEngine calls BOTH
    this function AND evaluate_risk() (which re-checks the same flag)
    as deliberate defense-in-depth, not because either alone is
    insufficient.
    """
    if manually_triggered:
        return RiskCheckResult(RiskState.BLOCKED, "Kill switch manually triggered.")
    if kill_switch_active:
        return RiskCheckResult(RiskState.BLOCKED, "Account-level kill switch is active — no trading permitted.")
    return RiskCheckResult(RiskState.OK, "Kill switch not active.")
