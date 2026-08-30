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
from app.technical_engine.features import calculate_feature_snapshots
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


@router.get("/features")
async def get_features(
    symbol: str = Query(..., examples=["EUR/USD"]),
    timeframe: str = Query(..., examples=["1h"]),
    limit: int = Query(default=500, le=5000),
) -> dict:
    """
    Phase 5's extended research feature set: SMA10/50, slope, distance,
    RSI14, ATR14, recent high/low, and an algorithmic regime label.

    Returns null for any value still in its warm-up period, and
    "UNKNOWN" for regime during warm-up. Never returns a BUY/SELL/WAIT
    decision — see /strategy/crossover-signals for that.
    """
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

    snapshots = calculate_feature_snapshots(candles)

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "features": [
            {
                "timestamp": s.timestamp.isoformat(),
                "close": s.close,
                "sma_10": s.sma_10,
                "sma_50": s.sma_50,
                "sma_50_slope": s.sma_50_slope,
                "sma_distance": s.sma_distance,
                "sma_distance_pct": s.sma_distance_pct,
                "rsi_14": s.rsi_14,
                "atr_14": s.atr_14,
                "atr_percent": s.atr_percent,
                "recent_high": s.recent_high,
                "recent_low": s.recent_low,
                "rolling_range": s.rolling_range,
                "distance_from_high": s.distance_from_high,
                "distance_from_low": s.distance_from_low,
                "regime": s.regime,
            }
            for s in snapshots
        ],
    }
