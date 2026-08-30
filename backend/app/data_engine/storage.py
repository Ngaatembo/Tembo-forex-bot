"""
Persists Candle objects into the market_candles table.

Uses PostgreSQL's ON CONFLICT DO NOTHING keyed on (symbol, timeframe,
timestamp) so ingestion is idempotent — re-running it for an
overlapping date range is safe and just fills gaps, never duplicates
or errors.
"""

from sqlalchemy import UniqueConstraint
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.data_engine.market_data import Candle
from app.database.models import MarketCandle

logger = get_logger(__name__)


async def store_candles(session: AsyncSession, candles: list[Candle]) -> int:
    """Returns the number of NEW rows actually inserted (duplicates are skipped, not errors)."""
    if not candles:
        return 0

    rows = [
        {
            "symbol": c.symbol,
            "timeframe": c.timeframe,
            "timestamp": c.timestamp,
            "open": c.open,
            "high": c.high,
            "low": c.low,
            "close": c.close,
            "volume": c.volume,
        }
        for c in candles
    ]

    stmt = insert(MarketCandle).values(rows)
    stmt = stmt.on_conflict_do_nothing(index_elements=["symbol", "timeframe", "timestamp"])
    result = await session.execute(stmt)
    await session.commit()

    inserted = result.rowcount or 0
    logger.info(
        "store_candles: %d/%d candles newly inserted (%d already existed)",
        inserted,
        len(rows),
        len(rows) - inserted,
    )
    return inserted
