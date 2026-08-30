"""
Phase 1 ingestion entrypoint.

Usage (once MARKET_DATA_PROVIDER=oanda and real credentials are set):

    python -m app.data_engine.ingest --symbol EUR/USD --timeframe 1h \\
        --start 2024-01-01 --end 2024-06-01

Pipeline: fetch -> normalize -> validate -> store. Validation problems
are printed and the run STOPS before storing anything if OHLC
violations, bad prices, or duplicate timestamps are found — those
mean the data itself is broken and must not enter the database
silently. Gaps are printed as a warning only, since weekend market
closures are expected in forex data.
"""

import argparse
import asyncio
from datetime import datetime, timezone

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.data_engine.market_data import get_market_data_provider
from app.data_engine.normalizer import normalize_candles
from app.data_engine.storage import store_candles
from app.data_engine.validator import validate_candles
from app.database.session import AsyncSessionLocal

logger = get_logger(__name__)


async def ingest(symbol: str, timeframe: str, start: datetime, end: datetime) -> None:
    settings = get_settings()
    provider = get_market_data_provider(settings.market_data_provider)

    logger.info("Fetching %s %s from %s to %s via %s", symbol, timeframe, start, end, settings.market_data_provider)
    raw_candles = await provider.get_historical_data(symbol, timeframe, start, end)
    logger.info("Fetched %d raw candles", len(raw_candles))

    if not raw_candles:
        logger.warning("No candles returned — nothing to do.")
        return

    normalized = normalize_candles(raw_candles)
    logger.info("Normalized to %d candles (deduped/sorted)", len(normalized))

    report = validate_candles(normalized, timeframe)
    logger.info(
        "Validation: %d total | %d OHLC violations | %d bad prices | %d dup timestamps | %d gaps",
        report.total_candles,
        len(report.ohlc_violations),
        len(report.negative_or_zero_price),
        len(report.duplicate_timestamps),
        len(report.unexpected_gaps),
    )

    for gap in report.unexpected_gaps:
        logger.warning("Unexpected gap: %s", gap)

    if not report.is_clean:
        for v in report.ohlc_violations:
            logger.error("OHLC violation: %s", v)
        for v in report.negative_or_zero_price:
            logger.error("Bad price: %s", v)
        for v in report.duplicate_timestamps:
            logger.error("Duplicate timestamp: %s", v)
        logger.error("Validation failed — refusing to store this batch. Fix the source data first.")
        return

    async with AsyncSessionLocal() as session:
        inserted = await store_candles(session, normalized)
    logger.info("Stored %d new candles (rest already existed).", inserted)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest historical forex candles.")
    parser.add_argument("--symbol", default="EUR/USD")
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument("--start", required=True, help="YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="YYYY-MM-DD")
    args = parser.parse_args()

    configure_logging("INFO")
    start = datetime.strptime(args.start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    end = datetime.strptime(args.end, "%Y-%m-%d").replace(tzinfo=timezone.utc)

    asyncio.run(ingest(args.symbol, args.timeframe, start, end))


if __name__ == "__main__":
    main()
