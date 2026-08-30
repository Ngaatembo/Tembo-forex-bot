"""
GET /strategy/crossover-signals

Returns the moving-average crossover strategy's BUY/SELL/WAIT signals
for stored candles. This endpoint does NOT place any order, paper or
live — it only reports what the strategy would have signaled. Phase 4
(backtesting) is what actually simulates trading on these signals.
"""

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from app.data_engine.market_data import Candle
from app.database.models import MarketCandle
from app.database.session import AsyncSessionLocal
from app.strategy_engine.service import run_crossover_strategy

router = APIRouter(prefix="/strategy", tags=["strategy"])


@router.get("/crossover-signals")
async def get_crossover_signals(
    symbol: str = Query(..., examples=["EUR/USD"]),
    timeframe: str = Query(..., examples=["1h"]),
    limit: int = Query(default=500, le=5000),
) -> dict:
    async with AsyncSessionLocal() as session:
        stmt = (
            select(MarketCandle)
            .where(MarketCandle.symbol == symbol, MarketCandle.timeframe == timeframe)
            .order_by(MarketCandle.timestamp.asc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        rows = result.scalars().all()

    if not rows:
        raise HTTPException(status_code=404, detail=f"No stored candles for {symbol} {timeframe}")

    candles = [
        Candle(
            symbol=r.symbol, timeframe=r.timeframe, timestamp=r.timestamp,
            open=r.open, high=r.high, low=r.low, close=r.close, volume=r.volume,
        )
        for r in rows
    ]

    signals = run_crossover_strategy(candles, symbol=symbol)

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "strategy": "sma_10_50_crossover",
        "signals": [
            {
                "timestamp": s.timestamp.isoformat(),
                "direction": s.direction,
                "sma_10": s.sma_10,
                "sma_50": s.sma_50,
                "reason": s.reason,
            }
            for s in signals
        ],
    }
