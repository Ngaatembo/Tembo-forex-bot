"""
GET /market-data/candles

Read-only access to stored candles. This is the only way the rest of
the system (technical engine, backtester, dashboard) should ever read
market data — nothing outside app/data_engine talks to the database
or a broker directly.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.database.models import MarketCandle
from app.database.session import AsyncSessionLocal

router = APIRouter(prefix="/market-data", tags=["market-data"])


@router.get("/candles")
async def get_candles(
    symbol: str = Query(..., examples=["EUR/USD"]),
    timeframe: str = Query(..., examples=["1h"]),
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    limit: int = Query(default=500, le=5000),
) -> list[dict]:
    async with AsyncSessionLocal() as session:
        # Return the most recent stored bars by default. The previous
        # implementation selected the oldest rows, which made the cockpit
        # appear stuck on historical data after a larger dataset was ingested.
        stmt = (
            select(MarketCandle)
            .where(MarketCandle.symbol == symbol, MarketCandle.timeframe == timeframe)
            .order_by(MarketCandle.timestamp.desc())
            .limit(limit)
        )
        if start is not None:
            stmt = stmt.where(MarketCandle.timestamp >= start)
        if end is not None:
            stmt = stmt.where(MarketCandle.timestamp <= end)

        result = await session.execute(stmt)
        candles = result.scalars().all()

    candles = list(reversed(candles))

    return [
        {
            "timestamp": c.timestamp.isoformat(),
            "open": c.open,
            "high": c.high,
            "low": c.low,
            "close": c.close,
            "volume": c.volume,
        }
        for c in candles
    ]
