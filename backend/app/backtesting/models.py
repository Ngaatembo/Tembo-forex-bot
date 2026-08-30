"""
Output shapes for the backtesting engine: Trade (one closed position),
EquityPoint (account state after one candle), BacktestSummary
(aggregate metrics), and BacktestResult (all of the above, plus the
configuration that produced them — a result is meaningless without
knowing exactly what config generated it).
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from app.backtesting.config import BacktestConfig

Direction = Literal["LONG", "SHORT"]


@dataclass
class Trade:
    trade_id: int
    symbol: str
    direction: Direction
    signal_timestamp: datetime       # when the crossover was detected
    entry_timestamp: datetime        # when the order actually executed (next candle)
    entry_price: float               # actual execution price, includes spread/slippage
    exit_timestamp: datetime
    exit_price: float                # actual execution price, includes spread/slippage
    size: float
    gross_pnl: float                 # P&L using mid prices, no costs
    transaction_costs: float         # gross_pnl - net_pnl (always >= 0)
    net_pnl: float                   # what actually happened to the account
    return_pct: float                # net_pnl / (entry_price * size)
    entry_reason: str
    exit_reason: str


@dataclass
class EquityPoint:
    timestamp: datetime
    balance: float          # realized cash — only changes when a trade closes
    equity: float           # balance + unrealized P&L of any open position
    drawdown: float         # peak_equity_so_far - equity, always >= 0
    drawdown_percent: float


@dataclass
class BacktestSummary:
    initial_balance: float
    final_balance: float
    net_pnl: float
    total_return: float
    trade_count: int

    # All of the following are None when trade_count == 0 or the
    # specific denominator is zero — never a fabricated/misleading
    # number. See metrics.py for exactly which conditions null each one.
    winning_trades: int | None = None
    losing_trades: int | None = None
    win_rate: float | None = None
    average_win: float | None = None
    average_loss: float | None = None
    largest_win: float | None = None
    largest_loss: float | None = None
    average_trade: float | None = None
    expectancy: float | None = None
    max_consecutive_wins: int | None = None
    max_consecutive_losses: int | None = None
    profit_factor: float | None = None
    max_drawdown: float | None = None
    max_drawdown_percent: float | None = None


@dataclass
class BacktestResult:
    configuration: BacktestConfig
    summary: BacktestSummary
    trades: list[Trade] = field(default_factory=list)
    equity_curve: list[EquityPoint] = field(default_factory=list)
