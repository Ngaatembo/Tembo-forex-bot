"""
POST /backtests/sma-crossover

Runs the SMA10/50 crossover strategy through the backtesting engine
against stored historical candles and returns the full result.

This endpoint ONLY simulates. It has no import of, and no code path
to, the live/paper execution layer — nothing here can place a real or
paper order. See tests/test_backtest_security_boundary.py, which
verifies this at the source-code level, not just by convention.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.backtesting.config import BacktestConfig
from app.backtesting.engine import run_backtest
from app.data_engine.market_data import Candle
from app.database.models import MarketCandle
from app.database.session import AsyncSessionLocal

router = APIRouter(prefix="/backtests", tags=["backtesting"])


class BacktestRequest(BaseModel):
    symbol: str = "EUR/USD"
    timeframe: str = "1h"
    start: Optional[datetime] = None
    end: Optional[datetime] = None
    initial_balance: float = Field(default=1000.0, gt=0)
    position_size: float = Field(default=10_000.0, gt=0)
    spread: float = Field(default=0.00010, ge=0)
    slippage: float = Field(default=0.0, ge=0)


@router.post("/sma-crossover")
async def backtest_sma_crossover(request: BacktestRequest) -> dict:
    async with AsyncSessionLocal() as session:
        stmt = (
            select(MarketCandle)
            .where(MarketCandle.symbol == request.symbol, MarketCandle.timeframe == request.timeframe)
            .order_by(MarketCandle.timestamp.asc())
        )
        if request.start is not None:
            stmt = stmt.where(MarketCandle.timestamp >= request.start)
        if request.end is not None:
            stmt = stmt.where(MarketCandle.timestamp <= request.end)

        result = await session.execute(stmt)
        rows = result.scalars().all()

    if not rows:
        raise HTTPException(
            status_code=404, detail=f"No stored candles for {request.symbol} {request.timeframe}"
        )

    candles = [
        Candle(
            symbol=r.symbol, timeframe=r.timeframe, timestamp=r.timestamp,
            open=r.open, high=r.high, low=r.low, close=r.close, volume=r.volume,
        )
        for r in rows
    ]

    config = BacktestConfig(
        symbol=request.symbol, timeframe=request.timeframe,
        initial_balance=request.initial_balance, position_size=request.position_size,
        spread=request.spread, slippage=request.slippage,
    )

    backtest_result = run_backtest(candles, config)

    return {
        "configuration": {
            "symbol": config.symbol, "timeframe": config.timeframe,
            "initial_balance": config.initial_balance, "position_size": config.position_size,
            "spread": config.spread, "slippage": config.slippage,
            "execution_model": config.execution_model, "end_of_data_policy": config.end_of_data_policy,
        },
        "summary": {
            "initial_balance": backtest_result.summary.initial_balance,
            "final_balance": backtest_result.summary.final_balance,
            "net_pnl": backtest_result.summary.net_pnl,
            "total_return": backtest_result.summary.total_return,
            "trade_count": backtest_result.summary.trade_count,
            "winning_trades": backtest_result.summary.winning_trades,
            "losing_trades": backtest_result.summary.losing_trades,
            "win_rate": backtest_result.summary.win_rate,
            "average_win": backtest_result.summary.average_win,
            "average_loss": backtest_result.summary.average_loss,
            "largest_win": backtest_result.summary.largest_win,
            "largest_loss": backtest_result.summary.largest_loss,
            "average_trade": backtest_result.summary.average_trade,
            "expectancy": backtest_result.summary.expectancy,
            "max_consecutive_wins": backtest_result.summary.max_consecutive_wins,
            "max_consecutive_losses": backtest_result.summary.max_consecutive_losses,
            "profit_factor": backtest_result.summary.profit_factor,
            "max_drawdown": backtest_result.summary.max_drawdown,
            "max_drawdown_percent": backtest_result.summary.max_drawdown_percent,
        },
        "trades": [
            {
                "trade_id": t.trade_id, "direction": t.direction,
                "signal_timestamp": t.signal_timestamp.isoformat(),
                "entry_timestamp": t.entry_timestamp.isoformat(), "entry_price": t.entry_price,
                "exit_timestamp": t.exit_timestamp.isoformat(), "exit_price": t.exit_price,
                "size": t.size, "gross_pnl": t.gross_pnl, "transaction_costs": t.transaction_costs,
                "net_pnl": t.net_pnl, "return_pct": t.return_pct,
                "entry_reason": t.entry_reason, "exit_reason": t.exit_reason,
            }
            for t in backtest_result.trades
        ],
        "equity_curve": [
            {
                "timestamp": p.timestamp.isoformat(), "balance": p.balance, "equity": p.equity,
                "drawdown": p.drawdown, "drawdown_percent": p.drawdown_percent,
            }
            for p in backtest_result.equity_curve
        ],
    }
