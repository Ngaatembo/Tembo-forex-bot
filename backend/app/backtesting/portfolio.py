"""
Portfolio: tracks the single open position (if any), realized balance,
and the equity curve. This is where the spread/slippage cost model
lives and where P&L is actually computed — the engine (engine.py) only
decides *when* to call these methods, never *how* P&L is calculated.

COST MODEL (documented explicitly, per Phase 4 spec section 10-12):

Every execution price is derived from the candle's mid price (its
open, per the next_open execution model) plus a bid/ask half-spread
and a fixed slippage, both always working AGAINST the trader:

  - Buying (LONG entry, or SHORT exit/"buying to cover"):
        execution_price = mid + spread/2 + slippage
  - Selling (SHORT entry, or LONG exit/"selling to close"):
        execution_price = mid - spread/2 - slippage

`gross_pnl` on a trade is computed from the two mid prices only (as if
costs were zero). `net_pnl` is computed from the two actual execution
prices. `transaction_costs = gross_pnl - net_pnl` is always >= 0 and
is reported on every trade separately, never folded silently into P&L.
"""

from dataclasses import dataclass
from datetime import datetime

from app.backtesting.config import BacktestConfig
from app.backtesting.models import EquityPoint, Trade


@dataclass
class _OpenPosition:
    direction: str  # "LONG" | "SHORT"
    size: float
    entry_mid_price: float
    entry_exec_price: float
    entry_timestamp: datetime
    signal_timestamp: datetime
    entry_reason: str
    # Phase 6 additions — all default to None/unset, so any code that
    # constructs a position without them (i.e. every Phase 4 baseline
    # call site) behaves EXACTLY as before. Only the new Phase 6
    # exit-rule engine (engine_research.py) ever sets these.
    stop_price: float | None = None
    target_price: float | None = None
    entry_candle_index: int | None = None
    max_holding_candles: int | None = None


class Portfolio:
    def __init__(self, config: BacktestConfig):
        self.config = config
        self.balance = config.initial_balance
        self.position: _OpenPosition | None = None
        self.trades: list[Trade] = []
        self.equity_curve: list[EquityPoint] = []
        self._next_trade_id = 1
        self._peak_equity = config.initial_balance

    def _execution_price(self, mid_price: float, *, is_buy_side: bool) -> float:
        half_spread = self.config.spread / 2
        if is_buy_side:
            return mid_price + half_spread + self.config.slippage
        return mid_price - half_spread - self.config.slippage

    def open_position(
        self, *, direction: str, mid_price: float, timestamp: datetime,
        signal_timestamp: datetime, reason: str,
        stop_price: float | None = None, target_price: float | None = None,
        entry_candle_index: int | None = None, max_holding_candles: int | None = None,
    ) -> None:
        if self.position is not None:
            raise RuntimeError(
                "open_position called while a position is already open — "
                "the engine must close/reverse before opening."
            )
        is_buy_side = direction == "LONG"
        exec_price = self._execution_price(mid_price, is_buy_side=is_buy_side)
        self.position = _OpenPosition(
            direction=direction, size=self.config.position_size,
            entry_mid_price=mid_price, entry_exec_price=exec_price,
            entry_timestamp=timestamp, signal_timestamp=signal_timestamp,
            entry_reason=reason,
            stop_price=stop_price, target_price=target_price,
            entry_candle_index=entry_candle_index, max_holding_candles=max_holding_candles,
        )

    def close_position(self, *, mid_price: float, timestamp: datetime, reason: str) -> Trade:
        if self.position is None:
            raise RuntimeError("close_position called with no open position.")
        pos = self.position
        is_buy_side = pos.direction == "SHORT"  # buying to cover a short
        exec_price = self._execution_price(mid_price, is_buy_side=is_buy_side)

        sign = 1 if pos.direction == "LONG" else -1
        gross_pnl = (mid_price - pos.entry_mid_price) * pos.size * sign
        net_pnl = (exec_price - pos.entry_exec_price) * pos.size * sign
        transaction_costs = gross_pnl - net_pnl

        trade = Trade(
            trade_id=self._next_trade_id,
            symbol=self.config.symbol,
            direction=pos.direction,
            signal_timestamp=pos.signal_timestamp,
            entry_timestamp=pos.entry_timestamp,
            entry_price=pos.entry_exec_price,
            exit_timestamp=timestamp,
            exit_price=exec_price,
            size=pos.size,
            gross_pnl=gross_pnl,
            transaction_costs=transaction_costs,
            net_pnl=net_pnl,
            return_pct=net_pnl / (pos.entry_exec_price * pos.size),
            entry_reason=pos.entry_reason,
            exit_reason=reason,
        )
        self._next_trade_id += 1
        self.balance += net_pnl
        self.trades.append(trade)
        self.position = None
        return trade

    def check_exit_conditions(self, *, candle_high: float, candle_low: float, candle_index: int) -> str | None:
        """
        Phase 6 addition. Checks whether the currently open position's
        stop-loss, take-profit, or max-holding-period condition was hit
        WITHIN this candle (using its high/low, not just its close —
        a stop can be touched intra-candle even if price closes back
        above it). Returns a reason string if so, else None.

        Only ever called by the Phase 6 research engine — the Phase 4
        baseline engine never calls this, so baseline trades are
        completely unaffected by this method's existence.

        ORDERING ASSUMPTION (documented, not hidden): if BOTH the stop
        and the target fall within the same candle's high-low range,
        this checks the stop FIRST — the conservative assumption that
        we can't know which was hit first within the candle, and
        assuming the worse outcome avoids overstating results.
        """
        pos = self.position
        if pos is None:
            return None

        if pos.stop_price is not None:
            if pos.direction == "LONG" and candle_low <= pos.stop_price:
                return "STOP_LOSS"
            if pos.direction == "SHORT" and candle_high >= pos.stop_price:
                return "STOP_LOSS"

        if pos.target_price is not None:
            if pos.direction == "LONG" and candle_high >= pos.target_price:
                return "TAKE_PROFIT"
            if pos.direction == "SHORT" and candle_low <= pos.target_price:
                return "TAKE_PROFIT"

        if pos.max_holding_candles is not None and pos.entry_candle_index is not None:
            if candle_index - pos.entry_candle_index >= pos.max_holding_candles:
                return "MAX_HOLDING_PERIOD"

        return None

    def close_position_at_price(self, *, exact_price: float, timestamp: datetime, reason: str) -> Trade:
        """
        Phase 6 addition. Closes at an EXACT price (the stop/target
        level itself) rather than deriving execution price from a mid
        + spread/slippage model — this represents a stop/limit order
        filling at its trigger price. Spread/slippage are still
        documented as NOT applied here; this is a simplification
        (real stop orders can slip past their trigger in fast markets)
        — see docs/phase-6-notes.md for this limitation.
        """
        if self.position is None:
            raise RuntimeError("close_position_at_price called with no open position.")
        pos = self.position
        sign = 1 if pos.direction == "LONG" else -1
        pnl = (exact_price - pos.entry_exec_price) * pos.size * sign

        trade = Trade(
            trade_id=self._next_trade_id, symbol=self.config.symbol, direction=pos.direction,
            signal_timestamp=pos.signal_timestamp, entry_timestamp=pos.entry_timestamp,
            entry_price=pos.entry_exec_price, exit_timestamp=timestamp, exit_price=exact_price,
            size=pos.size, gross_pnl=pnl, transaction_costs=0.0, net_pnl=pnl,
            return_pct=pnl / (pos.entry_exec_price * pos.size),
            entry_reason=pos.entry_reason, exit_reason=reason,
        )
        self._next_trade_id += 1
        self.balance += pnl
        self.trades.append(trade)
        self.position = None
        return trade

    def mark_to_market(self, *, mid_price: float, timestamp: datetime) -> EquityPoint:
        """Records one equity-curve point. Uses the mid price only — an
        open position's unrealized P&L is a paper valuation, not a
        realized cost, so spread/slippage are deliberately not applied
        here (they're only ever charged when a trade actually executes)."""
        unrealized = 0.0
        if self.position is not None:
            sign = 1 if self.position.direction == "LONG" else -1
            unrealized = (mid_price - self.position.entry_mid_price) * self.position.size * sign

        equity = self.balance + unrealized
        self._peak_equity = max(self._peak_equity, equity)
        drawdown = self._peak_equity - equity
        drawdown_percent = drawdown / self._peak_equity if self._peak_equity > 0 else 0.0

        point = EquityPoint(
            timestamp=timestamp, balance=self.balance, equity=equity,
            drawdown=drawdown, drawdown_percent=drawdown_percent,
        )
        self.equity_curve.append(point)
        return point
