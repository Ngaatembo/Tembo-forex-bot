"""Persistent historical-candle ingestion for PostgreSQL backtests.

The ingestion path is deliberately separate from live/paper execution.
It fetches bounded, completed H1 windows from the configured market-data
provider, validates them, and idempotently inserts them into market_candles.

Twelve Data's documented maximum is 5,000 data points per request. When
start_date and end_date are supplied together, outputsize must be omitted;
therefore callers should use bounded windows that stay below 5,000 H1
records (150 days is safely below that ceiling).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy.dialects.postgresql import insert

from app.core.logging import get_logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.data_engine.market_data import Candle, MarketDataProvider
from app.data_engine.validator import validate_candles
from app.database.models import MarketCandle

H1_WINDOW_DAYS = 150
MIN_REQUEST_SPACING_SECONDS = 8.0
SUPPORTED_HISTORICAL_INSTRUMENTS = ("EUR/USD", "GBP/USD", "XAU/USD")
logger = get_logger(__name__)

# A historical provider can occasionally return an isolated malformed bar.
# We never repair its prices. We may quarantine a very small number of bad
# rows, but only when the clean-data ratio is overwhelmingly high. If a
# provider returns a materially corrupted batch, ingestion still fails closed.
MAX_QUARANTINED_CANDLE_RATIO = 0.005  # 0.5%
MIN_CANDLES_FOR_QUARANTINE = 100
DB_INSERT_BATCH_SIZE = 1000


def _completed_h1(candles: list[Candle], now: datetime | None = None) -> list[Candle]:
    """Keep only fully closed H1 candles and return them chronologically."""
    now = now or datetime.now(timezone.utc)
    cutoff = now.replace(minute=0, second=0, microsecond=0)
    return [c for c in candles if c.timestamp + timedelta(hours=1) <= cutoff]


def _chunk_ranges(start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
    ranges: list[tuple[datetime, datetime]] = []
    cursor = start
    while cursor < end:
        chunk_end = min(cursor + timedelta(days=H1_WINDOW_DAYS), end)
        ranges.append((cursor, chunk_end))
        cursor = chunk_end
    return ranges


async def ingest_instrument(
    session: AsyncSession,
    provider: MarketDataProvider,
    symbol: str,
    start: datetime,
    end: datetime,
    request_spacing_seconds: float = MIN_REQUEST_SPACING_SECONDS,
) -> dict:
    if symbol not in SUPPORTED_HISTORICAL_INSTRUMENTS:
        raise ValueError(f"Unsupported historical instrument: {symbol}")
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("Historical ingestion requires timezone-aware start/end datetimes.")
    if end <= start:
        raise ValueError("Historical ingestion end must be after start.")

    ranges = _chunk_ranges(start.astimezone(timezone.utc), end.astimezone(timezone.utc))
    all_candles: dict[datetime, Candle] = {}

    for index, (chunk_start, chunk_end) in enumerate(ranges):
        candles = await provider.get_historical_data(symbol, "h1", chunk_start, chunk_end)
        for candle in _completed_h1(candles):
            all_candles[candle.timestamp] = candle
        if index < len(ranges) - 1 and request_spacing_seconds > 0:
            await asyncio.sleep(request_spacing_seconds)

    candles = sorted(all_candles.values(), key=lambda c: c.timestamp)
    report = validate_candles(candles, timeframe="h1")

    # Use the validator's reported row indices rather than reconstructing
    # the violation from floating-point values. This makes quarantine exact
    # even when provider values sit on floating-point comparison boundaries.
    bad_indices = {
        int(item.split(" ", 2)[1])
        for item in (report.ohlc_violations + report.negative_or_zero_price)
    }

    if bad_indices:
        bad_ratio = len(bad_indices) / max(len(candles), 1)
        can_quarantine = (
            len(candles) >= MIN_CANDLES_FOR_QUARANTINE
            and bad_ratio <= MAX_QUARANTINED_CANDLE_RATIO
            and not report.duplicate_timestamps
        )
        if not can_quarantine:
            raise ValueError(
                f"Historical data validation failed for {symbol}: "
                f"ohlc={len(report.ohlc_violations)}, "
                f"nonpositive={len(report.negative_or_zero_price)}, "
                f"duplicates={len(report.duplicate_timestamps)}, "
                f"bad_ratio={bad_ratio:.4%}"
            )

        original_count = len(candles)
        candles = [
            c for i, c in enumerate(candles)
            if i not in bad_indices
        ]
        logger.warning(
            "Historical data quarantined malformed candles: symbol=%s "
            "quarantined=%d total=%d ratio=%.4f",
            symbol,
            original_count - len(candles),
            original_count,
            bad_ratio,
        )

        # Re-validate the exact dataset that will be persisted. This prevents
        # a future validator change from accidentally allowing another class
        # of malformed row through.
        report = validate_candles(candles, timeframe="h1")
        if not report.is_clean:
            raise ValueError(
                f"Historical data validation failed after quarantine for {symbol}: "
                f"ohlc={len(report.ohlc_violations)}, "
                f"nonpositive={len(report.negative_or_zero_price)}, "
                f"duplicates={len(report.duplicate_timestamps)}"
            )

    if not candles:
        return {
            "symbol": symbol,
            "timeframe": "1h",
            "requested_start": start.astimezone(timezone.utc).isoformat(),
            "requested_end": end.astimezone(timezone.utc).isoformat(),
            "fetched_candles": 0,
            "inserted_candles": 0,
            "datasets": 0,
            "gaps_reported": len(report.unexpected_gaps),
        }

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
    inserted_candles = 0
    for offset in range(0, len(rows), DB_INSERT_BATCH_SIZE):
        batch = rows[offset : offset + DB_INSERT_BATCH_SIZE]
        stmt = insert(MarketCandle).values(batch)
        stmt = stmt.on_conflict_do_nothing(
            constraint="uq_market_candle_identity"
        )
        result = await session.execute(stmt)
        inserted_candles += int(result.rowcount or 0)

    await session.commit()

    return {
        "symbol": symbol,
        "timeframe": "1h",
        "requested_start": start.astimezone(timezone.utc).isoformat(),
        "requested_end": end.astimezone(timezone.utc).isoformat(),
        "fetched_candles": len(candles),
        "inserted_candles": inserted_candles,
        "datasets": 1,
        "gaps_reported": len(report.unexpected_gaps),
        "actual_start": candles[0].timestamp.isoformat(),
        "actual_end": candles[-1].timestamp.isoformat(),
        "data_quality": "clean",
    }


async def ingest_historical_range(
    session: AsyncSession,
    provider: MarketDataProvider,
    start: datetime,
    end: datetime,
    symbols: tuple[str, ...] = SUPPORTED_HISTORICAL_INSTRUMENTS,
    request_spacing_seconds: float = MIN_REQUEST_SPACING_SECONDS,
) -> dict:
    """Ingest all supported H1 instruments sequentially.

    Sequential instrument processing is intentional: the Basic Twelve Data
    plan has a small per-minute API credit quota, so parallel historical
    downloads would make rate-limit failures more likely.
    """
    results = []
    for symbol in symbols:
        results.append(
            await ingest_instrument(
                session,
                provider,
                symbol,
                start,
                end,
                request_spacing_seconds=request_spacing_seconds,
            )
        )
    return {
        "timeframe": "1h",
        "results": results,
        "fetched_candles": sum(r["fetched_candles"] for r in results),
        "inserted_candles": sum(r["inserted_candles"] for r in results),
    }
