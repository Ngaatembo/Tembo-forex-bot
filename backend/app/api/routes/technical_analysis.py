"""
GET /technical-analysis/sma

Reads validated candles through the existing market-data access layer
(the same query pattern as api/routes/market_data.py — this endpoint
does not talk to the database directly, and neither does the
technical engine it calls) and returns SMA10/SMA50 features.

Returns null for warm-up-period values. Never returns a BUY/SELL/WAIT
decision — that's the strategy engine's job, not built yet (Phase 3).
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from app.data_engine.market_data import Candle
from app.database.models import MarketCandle
from app.database.session import AsyncSessionLocal
from app.technical_engine.service import calculate_features

router = APIRouter(prefix="/technical-analysis", tags=["technical-analysis"])


@router.get("/sma")
async def get_sma(
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

    features = calculate_features(candles)

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "features": [
            {
                "timestamp": f.timestamp.isoformat(),
                "close": f.close,
                "sma_10": f.sma_10,
                "sma_50": f.sma_50,
            }
            for f in features
        ],
    }
