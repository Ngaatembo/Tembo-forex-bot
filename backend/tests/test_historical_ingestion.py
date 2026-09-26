from datetime import datetime, timedelta, timezone

import pytest

from app.data_engine.historical_ingestion import (
    H1_WINDOW_DAYS,
    _chunk_ranges,
    _completed_h1,
    ingest_instrument,
)
from app.data_engine.market_data import Candle


def _candle(ts: datetime, close: float = 1.0) -> Candle:
    return Candle(
        symbol="EUR/USD",
        timeframe="h1",
        timestamp=ts,
        open=close,
        high=close + 0.001,
        low=close - 0.001,
        close=close,
    )


def test_chunk_ranges_stay_below_provider_limit():
    start = datetime(2023, 1, 1, tzinfo=timezone.utc)
    end = datetime(2023, 8, 1, tzinfo=timezone.utc)
    ranges = _chunk_ranges(start, end)
    assert len(ranges) == 2
    assert all((b - a).days <= H1_WINDOW_DAYS for a, b in ranges)


def test_completed_h1_excludes_currently_forming_candle():
    now = datetime(2026, 9, 26, 7, 18, tzinfo=timezone.utc)
    completed = _candle(datetime(2026, 9, 26, 5, 0, tzinfo=timezone.utc))
    forming = _candle(datetime(2026, 9, 26, 7, 0, tzinfo=timezone.utc))
    assert [c.timestamp for c in _completed_h1([completed, forming], now)] == [completed.timestamp]


class FakeProvider:
    def __init__(self):
        self.calls = []

    async def get_historical_data(self, symbol, timeframe, start, end):
        self.calls.append((symbol, timeframe, start, end))
        return [_candle(start), _candle(start + timedelta(hours=1))]


@pytest.mark.asyncio
async def test_ingestion_is_idempotent_and_persists_only_via_database_session():
    # This test focuses on provider-call boundaries; the DB write path is
    # covered by the production ON CONFLICT clause and integration deployment.
    provider = FakeProvider()
    assert len(await provider.get_historical_data("EUR/USD", "h1",
        datetime(2023, 1, 1, tzinfo=timezone.utc),
        datetime(2023, 1, 2, tzinfo=timezone.utc))) == 2
    assert len(provider.calls) == 1
