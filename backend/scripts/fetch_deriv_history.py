"""
Download historical candles from Deriv's public API into CSV files.

Deriv returns at most ~5000 candles per request, so the range is fetched in
windows. Output: <out-dir>/<INSTRUMENT>_<tf>.csv with ISO-8601 UTC timestamps.
Read-only market data; no account access.

  python -m scripts.fetch_deriv_history --out-dir data/deriv --start 2023-01-01 \
      --instruments EUR/USD,GBP/USD,USD/JPY,XAU/USD --timeframes m5,m15,h1,h4,d1
"""

import argparse
import asyncio
import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.data_engine.providers.deriv import DerivMarketDataProvider

GRANULARITY = {"m5": 300, "m15": 900, "h1": 3600, "h4": 14400, "d1": 86400}
WINDOW_CANDLES = 4000


async def fetch(provider, instrument, timeframe, start, end):
    step = timedelta(seconds=GRANULARITY[timeframe] * WINDOW_CANDLES)
    out, cursor = {}, start
    while cursor < end:
        window_end = min(cursor + step, end)
        for attempt in range(3):
            try:
                candles = await provider.get_historical_data(instrument, timeframe, cursor, window_end)
                break
            except Exception as exc:  # retry transient API errors
                if attempt == 2:
                    print(f"  ! {instrument} {timeframe} {cursor:%Y-%m-%d}: {exc}", flush=True)
                    candles = []
                await asyncio.sleep(3 * (attempt + 1))
        for c in candles:
            out[c.timestamp] = c
        cursor = window_end
        await asyncio.sleep(0.4)
    return [out[k] for k in sorted(out)]


async def main_async(args):
    provider = DerivMarketDataProvider()
    start = datetime.fromisoformat(args.start).replace(tzinfo=timezone.utc)
    end = datetime.now(timezone.utc)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for instrument in args.instruments.split(","):
        for tf in args.timeframes.split(","):
            candles = await fetch(provider, instrument, tf, start, end)
            path = out_dir / f"{instrument.replace('/', '')}_{tf}.csv"
            with path.open("w", newline="") as fh:
                w = csv.writer(fh)
                w.writerow(["timestamp", "open", "high", "low", "close"])
                for c in candles:
                    w.writerow([c.timestamp.isoformat(), c.open, c.high, c.low, c.close])
            first = candles[0].timestamp.date() if candles else "-"
            last = candles[-1].timestamp.date() if candles else "-"
            print(f"{instrument} {tf}: {len(candles)} candles {first} -> {last}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--start", default="2023-01-01")
    ap.add_argument("--instruments", default="EUR/USD,GBP/USD,USD/JPY,XAU/USD")
    ap.add_argument("--timeframes", default="m5,m15,h1,h4,d1")
    asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    main()
