"""
Post-2022 historical data exporter — RENDER ONLY.

This cannot run in the development sandbox: it needs a real
MARKET_DATA_API_KEY and real network access to api.twelvedata.com,
neither of which exist in that environment (confirmed directly:
no .env file, MARKET_DATA_PROVIDER defaults to mock, and a direct
curl to api.twelvedata.com returns HTTP 403 from that sandbox).

Uses the EXISTING TwelveDataProvider.get_historical_data() — no
second Twelve Data client. That method itself caps at 5000 candles
per call and does not paginate internally, so this script calls it
repeatedly with advancing date windows (a normal usage pattern for a
capped API, not a modification to the provider).

SECURITY: the API key is never printed, written to any output file,
or logged. TwelveDataProviderError and its subclasses already redact
the key from their own messages (see twelvedata.py); this script adds
a defensive redaction pass around any other exception too, in case
something unexpected leaks it into an error string.

Run on Render (Shell tab, or a one-off Job) with:
    cd backend
    python -m scripts.export_post_2022_historical_data
"""

import asyncio
import csv
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, ".")

from app.core.config import get_settings
from app.data_engine.providers.twelvedata import TwelveDataProvider, TwelveDataProviderError
from app.data_engine.validator import validate_candles

START = datetime(2023, 1, 1, tzinfo=timezone.utc)
INSTRUMENTS = {
    "EUR/USD": "EURUSD_H1_2023plus",
    "GBP/USD": "GBPUSD_H1_2023plus",
    "XAU/USD": "XAUUSD_H1_2023plus",
}
CHUNK_DAYS = 150
RATE_LIMIT_SLEEP_SECONDS = 1.5
OUTPUT_DIR = "../research/data/post_2022"


def end_of_last_complete_hour() -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)


async def fetch_all_chunks(provider, instrument, start, end):
    all_candles = []
    chunk_start = start
    while chunk_start < end:
        chunk_end = min(chunk_start + timedelta(days=CHUNK_DAYS), end)
        print(f"  fetching {instrument} {chunk_start.date()} to {chunk_end.date()}...")
        candles = await provider.get_historical_data(instrument, "h1", chunk_start, chunk_end)
        all_candles.extend(candles)
        await asyncio.sleep(RATE_LIMIT_SLEEP_SECONDS)
        chunk_start = chunk_end
    return all_candles


def dedupe_and_sort(candles):
    seen = {}
    for c in candles:
        seen[c.timestamp] = c
    return sorted(seen.values(), key=lambda c: c.timestamp)


def write_csv(candles, path):
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "open", "high", "low", "close", "volume"])
        for c in candles:
            writer.writerow([
                c.timestamp.isoformat(), c.open, c.high, c.low, c.close,
                c.volume if c.volume is not None else "",
            ])


def sha256_of_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


async def export_instrument(provider, instrument, filename_base):
    print(f"=== {instrument} ===")
    requested_start = START
    requested_end = end_of_last_complete_hour()

    raw_candles = await fetch_all_chunks(provider, instrument, requested_start, requested_end)
    candles = dedupe_and_sort(raw_candles)

    report = validate_candles(candles, timeframe="h1")

    csv_path = f"{OUTPUT_DIR}/{filename_base}.csv"
    write_csv(candles, csv_path)
    csv_sha256 = sha256_of_file(csv_path)

    metadata = {
        "provider": "Twelve Data",
        "instrument": instrument,
        "timeframe": "h1",
        "requested_start": requested_start.isoformat(),
        "requested_end": requested_end.isoformat(),
        "actual_start": candles[0].timestamp.isoformat() if candles else None,
        "actual_end": candles[-1].timestamp.isoformat() if candles else None,
        "candle_count": len(candles),
        "timezone_handling": (
            "Twelve Data timestamps treated as UTC, matching the existing "
            "TwelveDataProvider's established assumption "
            "(app/data_engine/providers/twelvedata.py) -- not independently "
            "re-verified against Twelve Data's own timezone metadata in this export."
        ),
        "csv_sha256": csv_sha256,
        "export_timestamp": datetime.now(timezone.utc).isoformat(),
        "data_quality": {
            "is_clean": report.is_clean,
            "ohlc_violations": len(report.ohlc_violations),
            "negative_or_zero_price": len(report.negative_or_zero_price),
            "duplicate_timestamps": len(report.duplicate_timestamps),
            "unexpected_gaps": len(report.unexpected_gaps),
            "gap_details_sample": report.unexpected_gaps[:20],
        },
        "warnings": [],
    }
    if not report.is_clean:
        metadata["warnings"].append("Data quality issues found -- see data_quality section. Review before use in Experiment 3.")
    if len(candles) < 100:
        metadata["warnings"].append("Very low candle count -- export may have failed partially.")

    meta_path = f"{OUTPUT_DIR}/{filename_base}_metadata.json"
    with open(meta_path, "w") as f:
        json.dump(metadata, f, indent=2, default=str)

    print(f"  {len(candles)} candles, {metadata['actual_start']} to {metadata['actual_end']}")
    print(f"  data_quality.is_clean={report.is_clean}")
    print(f"  saved {csv_path} (sha256={csv_sha256[:12]}...)")
    print(f"  saved {meta_path}")
    return metadata


async def main():
    settings = get_settings()
    if settings.market_data_provider != "twelvedata":
        print(f"ERROR: MARKET_DATA_PROVIDER is {settings.market_data_provider!r}, expected 'twelvedata'.")
        return
    if not settings.market_data_api_key:
        print("ERROR: MARKET_DATA_API_KEY is not set.")
        return

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    provider = TwelveDataProvider()
    all_metadata = {}
    for instrument, filename_base in INSTRUMENTS.items():
        try:
            all_metadata[instrument] = await export_instrument(provider, instrument, filename_base)
        except TwelveDataProviderError as e:
            print(f"  FAILED for {instrument}: {e}")
            all_metadata[instrument] = {"error": str(e)}
        except Exception as e:
            key = settings.market_data_api_key
            msg = str(e).replace(key, "[REDACTED]") if key else str(e)
            print(f"  FAILED for {instrument}: {msg}")
            all_metadata[instrument] = {"error": msg}

    summary_path = f"{OUTPUT_DIR}/export_summary.json"
    with open(summary_path, "w") as f:
        json.dump(all_metadata, f, indent=2, default=str)
    print(f"\nDone. Summary at {summary_path}")


if __name__ == "__main__":
    asyncio.run(main())
