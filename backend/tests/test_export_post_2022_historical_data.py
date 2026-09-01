"""
Tests for scripts/export_post_2022_historical_data.py's own logic
(pagination/chunking, dedup, CSV writing) using a mocked provider —
this script cannot be tested against the real Twelve Data API from
this environment (no credentials, no network access), so these tests
prove the ORCHESTRATION logic is correct in isolation.
"""

import csv
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from scripts.export_post_2022_historical_data import (
    CHUNK_DAYS, dedupe_and_sort, end_of_last_complete_hour, fetch_all_chunks, sha256_of_file, write_csv,
)

from app.data_engine.market_data import Candle


def make_candle(ts: datetime, close: float = 1.10) -> Candle:
    return Candle(symbol="EUR/USD", timeframe="h1", timestamp=ts, open=close, high=close, low=close, close=close, volume=None)


def test_end_of_last_complete_hour_never_includes_current_forming_hour():
    result = end_of_last_complete_hour()
    now = datetime.now(timezone.utc)
    assert result < now
    assert result.minute == 0 and result.second == 0 and result.microsecond == 0


@pytest.mark.asyncio
async def test_fetch_all_chunks_calls_provider_once_per_chunk_when_range_exceeds_one_chunk():
    start = datetime(2023, 1, 1, tzinfo=timezone.utc)
    end = start + timedelta(days=400)

    call_ranges = []

    async def fake_get_historical_data(instrument, timeframe, chunk_start, chunk_end):
        call_ranges.append((chunk_start, chunk_end))
        return [make_candle(chunk_start)]

    provider = AsyncMock()
    provider.get_historical_data = fake_get_historical_data

    from scripts import export_post_2022_historical_data as mod
    mod.RATE_LIMIT_SLEEP_SECONDS = 0

    result = await fetch_all_chunks(provider, "EUR/USD", start, end)

    assert len(call_ranges) == 3
    assert call_ranges[0][0] == start
    assert call_ranges[0][1] == start + timedelta(days=CHUNK_DAYS)
    assert call_ranges[-1][1] == end
    assert len(result) == 3


@pytest.mark.asyncio
async def test_fetch_all_chunks_single_call_when_range_fits_in_one_chunk():
    start = datetime(2023, 1, 1, tzinfo=timezone.utc)
    end = start + timedelta(days=30)
    call_count = 0

    async def fake_get_historical_data(instrument, timeframe, chunk_start, chunk_end):
        nonlocal call_count
        call_count += 1
        return [make_candle(chunk_start)]

    provider = AsyncMock()
    provider.get_historical_data = fake_get_historical_data

    from scripts import export_post_2022_historical_data as mod
    mod.RATE_LIMIT_SLEEP_SECONDS = 0

    await fetch_all_chunks(provider, "EUR/USD", start, end)
    assert call_count == 1


def test_dedupe_and_sort_removes_exact_duplicate_timestamps():
    ts1 = datetime(2023, 1, 1, tzinfo=timezone.utc)
    ts2 = datetime(2023, 1, 1, 1, tzinfo=timezone.utc)
    candles = [make_candle(ts2), make_candle(ts1), make_candle(ts1)]
    result = dedupe_and_sort(candles)
    assert len(result) == 2
    assert result[0].timestamp == ts1
    assert result[1].timestamp == ts2


def test_dedupe_and_sort_chronological_order():
    ts_list = [datetime(2023, 1, 1, h, tzinfo=timezone.utc) for h in (5, 1, 3, 2, 4)]
    candles = [make_candle(ts) for ts in ts_list]
    result = dedupe_and_sort(candles)
    timestamps = [c.timestamp for c in result]
    assert timestamps == sorted(timestamps)


def test_write_csv_produces_readable_output(tmp_path):
    candles = [
        make_candle(datetime(2023, 1, 1, tzinfo=timezone.utc), close=1.10),
        make_candle(datetime(2023, 1, 1, 1, tzinfo=timezone.utc), close=1.11),
    ]
    path = tmp_path / "test.csv"
    write_csv(candles, str(path))

    with open(path) as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 2
    assert rows[0]["close"] == "1.1"
    assert "timestamp" in rows[0] and "open" in rows[0] and "volume" in rows[0]


def test_sha256_of_file_is_deterministic(tmp_path):
    path = tmp_path / "test.csv"
    path.write_text("hello world")
    hash1 = sha256_of_file(str(path))
    hash2 = sha256_of_file(str(path))
    assert hash1 == hash2
    assert len(hash1) == 64


def test_api_key_never_appears_in_export_script_source():
    import re
    with open("scripts/export_post_2022_historical_data.py") as f:
        content = f.read()
    assert not re.search(r"apikey\s*=\s*['\"][a-zA-Z0-9]{15,}", content)
    assert "github_pat_" not in content
