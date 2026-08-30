"""
Risk decision model — the shapes the Risk Engine (risk_engine.py)
produces and consumes. Pure data, no logic here.
"""

from dataclasses import asdict, dataclass
from typing import Optional

RISK_DECISION_STATES = frozenset({
    "APPROVED", "REJECTED", "NO_VALIDATED_EDGE", "RISK_LIMIT_EXCEEDED",
    "INSUFFICIENT_ACCOUNT_DATA", "INVALID_INSTRUMENT", "INVALID_STOP",
    "POSITION_TOO_LARGE", "KILL_SWITCH_ACTIVE",
})


@dataclass(frozen=True)
class RiskLimitsConfig:
    """
    Every default here is a documented, conservative STARTING point for
    research/paper trading — NOT a claim that this percentage
    guarantees safety or profitability. Configuration-driven so it can
    change without touching any strategy or risk-engine logic.
    """
    max_risk_per_trade_pct: float = 0.01
    max_total_open_risk_pct: float = 0.03
    max_daily_loss_pct: float = 0.03
    max_drawdown_pct: float = 0.15
    max_simultaneous_positions: int = 3
    max_exposure_pct: float = 0.50

    def __post_init__(self):
        for name, value in (
            ("max_risk_per_trade_pct", self.max_risk_per_trade_pct),
            ("max_total_open_risk_pct", self.max_total_open_risk_pct),
            ("max_daily_loss_pct", self.max_daily_loss_pct),
            ("max_drawdown_pct", self.max_drawdown_pct),
            ("max_exposure_pct", self.max_exposure_pct),
        ):
            if not (0 < value <= 1):
                raise ValueError(f"{name} must be in (0, 1], got {value}")
        if self.max_simultaneous_positions <= 0:
            raise ValueError("max_simultaneous_positions must be positive.")


@dataclass(frozen=True)
class AccountState:
    """
    A snapshot of account state, supplied by the caller — this module
    never queries a broker or maintains its own account state. Every
    field is Optional; missing data means INSUFFICIENT_ACCOUNT_DATA,
    never an assumed-safe default (e.g. missing equity is never
    treated as "equity is fine").
    """
    equity: Optional[float] = None
    peak_equity: Optional[float] = None
    daily_start_equity: Optional[float] = None
    daily_realized_pnl: float = 0.0
    daily_unrealized_pnl: float = 0.0
    open_positions_count: int = 0
    total_open_risk_pct: float = 0.0
    kill_switch_active: bool = True


@dataclass(frozen=True)
class PositionSizingDetail:
    sizing_model: str
    risk_amount: float
    stop_distance: float
    raw_position_size: float
    final_position_size: float
    notes: str = ""


@dataclass(frozen=True)
class RiskDecision:
    state: str
    reason: str
    position_sizing: Optional[PositionSizingDetail] = None
    computed_risk_pct: Optional[float] = None
    hierarchy_stage: str = ""

    def __post_init__(self):
        if self.state not in RISK_DECISION_STATES:
            raise ValueError(f"Unknown risk decision state {self.state!r}. Allowed: {sorted(RISK_DECISION_STATES)}")

    def to_dict(self) -> dict:
        return asdict(self)
