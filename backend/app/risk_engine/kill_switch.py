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


def check_kill_switch(*, manually_triggered: bool = False) -> RiskCheckResult:
    """
    Phase 0 placeholder: always returns BLOCKED with an explicit reason,
    since no real trading logic exists yet to safely allow OK. Later
    phases replace the body of this function with real checks
    (daily loss limit, drawdown, exposure, etc.) — every one of those
    checks must default to BLOCKED/UNKNOWN on any doubt, never OK.
    """
    if manually_triggered:
        return RiskCheckResult(RiskState.BLOCKED, "Kill switch manually triggered.")

    return RiskCheckResult(
        RiskState.BLOCKED,
        "No live or paper trading logic implemented yet (Phase 0). "
        "This is the expected/safe default.",
    )
