"""
Research-only risk configuration for Phase 6 experiments.

CRITICAL: this module is NEVER connected to the live/paper execution
layer or any order-placing code path. It exists purely to let position sizing
be an explicit, recorded experiment parameter rather than always
defaulting to BacktestConfig's fixed size. See
tests/test_backtest_security_boundary.py-style checks — a similar
check for this module is in tests/test_risk_config_security_boundary.py.

Two sizing models:

  FIXED — same notional size every trade, regardless of stop distance
    or account equity. This is what every Phase 4-6 baseline/exit
    experiment in this phase actually uses, DELIBERATELY: holding
    position size constant across experiments isolates the entry/exit
    rule as the only variable being tested. Changing sizing AND the
    exit rule in the same experiment would make it impossible to
    attribute a result to either one.

  PERCENT_OF_EQUITY — size = (equity * risk_pct) / stop_distance. Only
    meaningful when a stop-loss is defined (division by stop distance).
    Implemented and tested here, but NOT used in this phase's actual
    baseline-comparison experiments, for the isolation reason above —
    it's here for a future phase that specifically studies sizing.

FAIL-CLOSED: if percent-of-equity sizing is requested without a stop
distance, or with invalid inputs, this raises rather than silently
falling back to some default size.
"""

from dataclasses import dataclass
from typing import Literal

SizingModel = Literal["fixed", "percent_of_equity"]


@dataclass
class RiskConfig:
    model: SizingModel
    fixed_size: float | None = None
    risk_pct_of_equity: float | None = None
    max_position_size: float | None = None
    max_drawdown_halt_pct: float | None = None

    def __post_init__(self):
        if self.model == "fixed":
            if self.fixed_size is None or self.fixed_size <= 0:
                raise ValueError("model='fixed' requires a positive fixed_size.")
        elif self.model == "percent_of_equity":
            if self.risk_pct_of_equity is None or not (0 < self.risk_pct_of_equity <= 1):
                raise ValueError(
                    "model='percent_of_equity' requires risk_pct_of_equity in (0, 1]."
                )
        else:
            raise ValueError(f"Unknown sizing model: {self.model!r}")

        if self.max_position_size is not None and self.max_position_size <= 0:
            raise ValueError("max_position_size must be positive if set.")
        if self.max_drawdown_halt_pct is not None and not (0 < self.max_drawdown_halt_pct <= 1):
            raise ValueError("max_drawdown_halt_pct must be in (0, 1] if set.")


def compute_position_size(
    *, config: RiskConfig, current_equity: float, entry_price: float, stop_price: float | None,
) -> float:
    """
    Fails closed: returns 0.0 (no position — the caller must treat this
    as "do not open a trade") on any input that would otherwise force
    a guess — never a fabricated fallback size.
    """
    if config.model == "fixed":
        size = config.fixed_size
    else:  # percent_of_equity
        if stop_price is None:
            return 0.0  # cannot size without a defined stop distance
        stop_distance = abs(entry_price - stop_price)
        if stop_distance <= 0:
            return 0.0
        risk_amount = current_equity * config.risk_pct_of_equity
        size = risk_amount / stop_distance

    if config.max_position_size is not None:
        size = min(size, config.max_position_size)

    return size


def drawdown_halt_triggered(*, config: RiskConfig, current_drawdown_percent: float) -> bool:
    """Fail-closed check: if max_drawdown_halt_pct isn't configured,
    this returns False (no halt) — an explicit "not configured" state,
    not an assumed-safe default hiding a missing setting."""
    if config.max_drawdown_halt_pct is None:
        return False
    return current_drawdown_percent >= config.max_drawdown_halt_pct
