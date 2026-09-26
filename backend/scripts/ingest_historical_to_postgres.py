"""One-shot historical H1 ingestion into Render PostgreSQL.

Run from backend/ on the deployed environment:

    python -m scripts.ingest_historical_to_postgres

The script uses the existing TwelveDataProvider and persists only completed,
validated H1 candles. It is idempotent, so re-running it does not duplicate
candles. No API key is printed or written anywhere.

Environment:
  MARKET_DATA_PROVIDER=twelvedata
  MARKET_DATA_API_KEY=<existing Twelve Data key>
  DATABASE_URL=<existing Render PostgreSQL URL>

By default it loads 2023-01-01 through the last completed UTC H1 candle.
The ingestion is intentionally rate-limited for Twelve Data Basic's 8
API-credit/minute quota.
"""

import asyncio
import logging
from datetime import datetime, timezone

from app.core.config import get_settings
from app.data_engine.historical_ingestion import ingest_historical_range
from app.data_engine.providers.twelvedata import TwelveDataProvider
from app.database.init import initialize_database
from app.database.session import AsyncSessionLocal

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def last_completed_hour() -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(minute=0, second=0, microsecond=0) - __import__("datetime").timedelta(hours=1)


async def main() -> None:
    settings = get_settings()
    if settings.market_data_provider != "twelvedata":
        raise RuntimeError("MARKET_DATA_PROVIDER must be 'twelvedata' for historical ingestion.")
    if not settings.market_data_api_key:
        raise RuntimeError("MARKET_DATA_API_KEY is not configured.")

    start = datetime(2023, 1, 1, tzinfo=timezone.utc)
    end = last_completed_hour()

    await initialize_database()
    provider = TwelveDataProvider()
    try:
        async with AsyncSessionLocal() as session:
            result = await ingest_historical_range(session, provider, start, end)
            logger.info(
                "Historical ingestion complete: fetched=%s inserted=%s",
                result["fetched_candles"],
                result["inserted_candles"],
            )
            for item in result["results"]:
                logger.info(
                    "%s: fetched=%s inserted=%s range=%s..%s",
                    item["symbol"],
                    item["fetched_candles"],
                    item["inserted_candles"],
                    item.get("actual_start"),
                    item.get("actual_end"),
                )
    finally:
        await provider._client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
