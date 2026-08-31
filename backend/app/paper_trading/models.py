"""
Paper trading models. Pure data — no execution capability anywhere in
this file. A PaperPosition/PaperTrade can only ever be created by
app.paper_trading.engine.PaperTradingEngine, and only after Phase 14's
Strategy Selector AND Phase 15's Risk Engine both independently
approve — see engine.py's docstring for the full decision chain.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

DIRECTIONS = frozenset({"LONG", "SHORT"})


@dataclass
class PaperPosition:
    position_id: str
    instrument: str
    timeframe: str
    direction: str
    entry_price: float
    entry_time: datetime
    stop_price: float
    position_size: float
    candidate_config_id: str
    take_profit_price: Optional[float] = None
    max_holding_periods: Optional[int] = None
    periods_held: int = 0
    status: str = "OPEN"

    def __post_init__(self):
        if self.direction not in DIRECTIONS:
            raise ValueError(f"direction must be one of {DIRECTIONS}, got {self.direction!r}")
        if self.entry_price <= 0:
            raise ValueError("entry_price must be positive.")
        if self.position_size <= 0:
            raise ValueError("position_size must be positive.")

    def unrealized_pnl(self, current_price: float) -> float:
        if self.direction == "LONG":
            return (current_price - self.entry_price) * self.position_size
        return (self.entry_price - current_price) * self.position_size

    def key(self) -> str:
        return f"{self.instrument}:{self.timeframe}"


@dataclass
class PaperTrade:
    trade_id: str
    position_id: str
    instrument: str
    timeframe: str
    direction: str
    entry_price: float
    entry_time: datetime
    exit_price: float
    exit_time: datetime
    exit_reason: str
    position_size: float
    realized_pnl: float
    candidate_config_id: str
