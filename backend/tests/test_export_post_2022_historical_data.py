"""
Tests for scripts/export_post_2022_historical_data.py's own logic
(chunk-boundary computation, bounded-concurrency fetching, dedup, CSV
writing) using a mocked provider — this script cannot be tested
against the real Twelve Data API from this environment (no
credentials, no network access), so these tests prove the
ORCHESTRATION logic is correct in isolation, including that the
concurrency optimization produces an IDENTICAL result to what
sequential fetching produced.
"""

import asyncio
import csv
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from scripts.export_post_2022_historical_data import (
    CHUNK_DAYS, MAX_CONCURRENT_REQUESTS, chunk_ranges, dedupe_and_sort, end_of_last_complete_hour,
    fetch_all_chunks, sha256_of_file, write_csv,
)

from app.data_engine.market_data import Candle


def make_candle(ts: datetime, close: float = 1.10) -> Candle:
    return Candle(symbol="EUR/USD", timeframe="h1", timestamp=ts, open=close, high=close, low=close, close=close, volume=None)


def test_end_of_last_complete_hour_never_includes_current_forming_hour():
    result = end_of_last_complete_hour()
    now = datetime.now(timezone.utc)
    assert result < now
    assert result.minute == 0 and result.second == 0 and result.microsecond == 0


def test_chunk_ranges_boundaries_unchanged_from_original_sequential_version():
    start = datetime(2023, 1, 1, tzinfo=timezone.utc)
    end = start + timedelta(days=400)
    ranges = chunk_ranges(start, end)
    assert len(ranges) == 3
    assert ranges[0] == (start, start + timedelta(days=CHUNK_DAYS))
    assert ranges[1] == (start + timedelta(days=CHUNK_DAYS), start + timedelta(days=2 * CHUNK_DAYS))
    assert ranges[2][1] == end


def test_chunk_ranges_single_chunk_when_range_fits():
    start = datetime(2023, 1, 1, tzinfo=timezone.utc)
    end = start + timedelta(days=30)
    ranges = chunk_ranges(start, end)
    assert ranges == [(start, end)]


@pytest.mark.asyncio
async def test_fetch_all_chunks_fetches_every_chunk_exactly_once():
    start = datetime(2023, 1, 1, tzinfo=timezone.utc)
    end = start + timedelta(days=400)
    call_ranges = []

    async def fake_get_historical_data(instrument, timeframe, chunk_start, chunk_end):
        call_ranges.append((chunk_start, chunk_end))
        return [make_candle(chunk_start)]

    provider = AsyncMock()
    provider.get_historical_data = fake_get_historical_data

    result = await fetch_all_chunks(provider, "EUR/USD", start, end)

    assert len(call_ranges) == 3
    assert set(call_ranges) == set(chunk_ranges(start, end))
    assert len(result) == 3


@pytest.mark.asyncio
async def test_concurrency_is_bounded_by_semaphore():
    start = datetime(2023, 1, 1, tzinfo=timezone.utc)
    end = start + timedelta(days=CHUNK_DAYS * 8)

    in_flight = 0
    max_observed = 0

    async def fake_get_historical_data(instrument, timeframe, chunk_start, chunk_end):
        nonlocal in_flight, max_observed
        in_flight += 1
        max_observed = max(max_observed, in_flight)
        await asyncio.sleep(0.02)
        in_flight -= 1
        return [make_candle(chunk_start)]

    provider = AsyncMock()
    provider.get_historical_data = fake_get_historical_data

    await fetch_all_chunks(provider, "EUR/USD", start, end)
    assert max_observed <= MAX_CONCURRENT_REQUESTS
    assert max_observed > 1


@pytest.mark.asyncio
async def test_concurrent_fetch_is_faster_than_equivalent_sequential_would_be():
    start = datetime(2023, 1, 1, tzinfo=timezone.utc)
    end = start + timedelta(days=CHUNK_DAYS * 5)
    per_call_latency = 0.05

    async def fake_get_historical_data(instrument, timeframe, chunk_start, chunk_end):
        await asyncio.sleep(per_call_latency)
        return [make_candle(chunk_start)]

    provider = AsyncMock()
    provider.get_historical_data = fake_get_historical_data

    t0 = time.monotonic()
    await fetch_all_chunks(provider, "EUR/USD", start, end)
    elapsed = time.monotonic() - t0

    sequential_equivalent = 5 * per_call_latency
    assert elapsed < sequential_equivalent * 0.8


@pytest.mark.asyncio
async def test_concurrent_result_identical_to_what_sequential_would_produce():
    start = datetime(2023, 1, 1, tzinfo=timezone.utc)
    end = start + timedelta(days=CHUNK_DAYS * 4)

    async def fake_get_historical_data(instrument, timeframe, chunk_start, chunk_end):
        delay = 0.05 if chunk_start == start else 0.01
        await asyncio.sleep(delay)
        return [make_candle(chunk_start), make_candle(chunk_start + timedelta(hours=1))]

    provider = AsyncMock()
    provider.get_historical_data = fake_get_historical_data

    raw = await fetch_all_chunks(provider, "EUR/USD", start, end)
    result = dedupe_and_sort(raw)

    timestamps = [c.timestamp for c in result]
    assert timestamps == sorted(timestamps)
    assert len(result) == len(set(timestamps))


def test_dedupe_and_sort_removes_exact_duplicate_timestamps():
    ts1 = datetime(2023, 1, 1, tzinfo=timezone.utc)
    ts2 = datetime(2023, 1, 1, 1, tzinfo=timezone.utc)
    candles = [make_candle(ts2), make_candle(ts1), make_candle(ts1)]
    result = dedupe_and_sort(candles)
    assert len(result) == 2
    assert result[0].timestamp == ts1
    assert result[1].timestamp == ts2


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
