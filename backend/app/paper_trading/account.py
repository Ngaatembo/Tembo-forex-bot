"""
PaperAccountState — stateful, mutable, multi-position paper account.
Distinct from app.risk_engine.risk_models.AccountState (a per-decision
READ-ONLY SNAPSHOT the Risk Engine consumes) — this is the actual
account the Paper Trading Engine mutates over a position's lifecycle.
to_risk_engine_snapshot() builds the snapshot from current state.

Positions are keyed by "instrument:timeframe" (PaperPosition.key()) —
this is what makes "XAU/USD H1 + EUR/USD M15 + GBP/USD H4
simultaneously" work without one overwriting another, and is also
the duplicate-position guard: the same instrument/timeframe pair
cannot have two open positions at once.

DAILY P&L: for this milestone, "daily" realized/unrealized P&L are
simply the account's total realized_pnl and current unrealized P&L —
there is no multi-day session tracking yet (would require a real
persistent store across process restarts, out of scope here). This
is accurate for a single continuous session, which is all a
same-process paper engine can represent right now.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from app.paper_trading.models import PaperPosition, PaperTrade
from app.risk_engine.risk_models import AccountState as RiskEngineAccountState


@dataclass
class PaperAccountState:
    account_id: str
    initial_equity: float
    daily_start_equity: Optional[float] = None
    kill_switch_active: bool = False
    open_positions: dict = field(default_factory=dict)
    position_risk_amounts: dict = field(default_factory=dict)
    closed_trades: list = field(default_factory=list)
    realized_pnl: float = 0.0
    _peak_equity: float = field(default=None, repr=False)

    def __post_init__(self):
        if self.initial_equity <= 0:
            raise ValueError("initial_equity must be positive.")
        if self.daily_start_equity is None:
            self.daily_start_equity = self.initial_equity
        if self._peak_equity is None:
            self._peak_equity = self.initial_equity

    def _unrealized_pnl(self, current_prices: dict) -> float:
        total = 0.0
        for key, pos in self.open_positions.items():
            price = current_prices.get(key)
            if price is not None:
                total += pos.unrealized_pnl(price)
        return total

    def unrealized_pnl(self, current_prices: dict) -> float:
        return self._unrealized_pnl(current_prices)

    def equity(self, current_prices: dict) -> float:
        e = self.initial_equity + self.realized_pnl + self._unrealized_pnl(current_prices)
        if e > self._peak_equity:
            self._peak_equity = e
        return e

    def current_drawdown_pct(self, current_prices: dict) -> float:
        e = self.equity(current_prices)
        if self._peak_equity <= 0:
            return 0.0
        return max(0.0, (self._peak_equity - e) / self._peak_equity)

    def total_open_risk_amount(self) -> float:
        return sum(self.position_risk_amounts.values())

    def open_position(self, position: PaperPosition, risk_amount: float) -> None:
        key = position.key()
        if key in self.open_positions:
            raise ValueError(f"A position is already open for {key} — duplicate positions on the same instrument/timeframe are not allowed.")
        if risk_amount <= 0:
            raise ValueError("risk_amount must be positive.")
        self.open_positions[key] = position
        self.position_risk_amounts[key] = risk_amount

    def get_position(self, key: str) -> Optional[PaperPosition]:
        return self.open_positions.get(key)

    def close_position(self, key: str, exit_price: float, exit_time: datetime, exit_reason: str) -> PaperTrade:
        if key not in self.open_positions:
            raise KeyError(f"No open position for {key!r}.")
        pos = self.open_positions.pop(key)
        self.position_risk_amounts.pop(key, None)
        realized = pos.unrealized_pnl(exit_price)
        self.realized_pnl += realized
        trade = PaperTrade(
            trade_id=f"trade_{pos.position_id}", position_id=pos.position_id,
            instrument=pos.instrument, timeframe=pos.timeframe, direction=pos.direction,
            entry_price=pos.entry_price, entry_time=pos.entry_time, exit_price=exit_price,
            exit_time=exit_time, exit_reason=exit_reason, position_size=pos.position_size,
            realized_pnl=realized, candidate_config_id=pos.candidate_config_id,
        )
        self.closed_trades.append(trade)
        return trade

    def to_risk_engine_snapshot(self, current_prices: dict) -> RiskEngineAccountState:
        e = self.equity(current_prices)
        return RiskEngineAccountState(
            equity=e, peak_equity=self._peak_equity, daily_start_equity=self.daily_start_equity,
            daily_realized_pnl=self.realized_pnl,
            daily_unrealized_pnl=self._unrealized_pnl(current_prices),
            open_positions_count=len(self.open_positions),
            total_open_risk_pct=self.total_open_risk_amount() / e if e > 0 else 0.0,
            kill_switch_active=self.kill_switch_active,
        )
