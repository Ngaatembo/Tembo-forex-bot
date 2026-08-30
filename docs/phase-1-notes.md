# Phase 1 — Historical EUR/USD Data (complete)

## The pipeline, and why each stage exists

```
OANDA API  ->  normalize  ->  validate  ->  store  ->  expose via API
(fetch)        (consistent    (catch bad    (idempotent  (/market-data/candles)
                shape)         data early)   upsert)
```

**Fetch (`providers/oanda.py`)** — talks to OANDA's REST API. Paginates
automatically past OANDA's 5000-candle-per-request limit for wide date
ranges. Drops incomplete/in-progress candles — an unfinished bar must
never be treated as a finished historical one.

**Normalize (`normalizer.py`)** — makes every candle's *shape* trustworthy
before we ever ask whether its *content* is trustworthy: forces UTC,
rounds float noise, removes exact-duplicate timestamps, sorts
chronologically. This step never judges whether a price looks right —
only whether the data is in a consistent format.

**Validate (`validator.py`)** — this is the step most people skip, and
it's the one that actually protects your backtest later. It checks:
- OHLC sanity (high can't be below the close, etc. — this is
  mathematically impossible in real data, so it means something broke)
- No zero/negative prices (near-always a data outage, not a real quote)
- Gaps bigger than expected — but weekend closures (~48h) are normal
  in forex, so those are explicitly *not* flagged as errors, only
  genuinely unexplained gaps are

**Store (`storage.py`)** — upserts into PostgreSQL keyed on
`(symbol, timeframe, timestamp)`. Re-running ingestion for an
overlapping date range is safe — duplicates are silently skipped,
never re-inserted or errored on.

**Expose (`api/routes/market_data.py`)** — `GET /market-data/candles`
is the only sanctioned way anything else in the system (Phase 2's
indicators, the eventual backtester, the dashboard) reads price data.
Nothing outside `data_engine` should ever query the database or a
broker directly — that boundary is what makes it possible to swap
brokers later without touching strategy code.

## Why validation failures block storage entirely

If OHLC violations, bad prices, or duplicate timestamps are found,
`ingest.py` refuses to store *any* of that batch — not just the bad
candles. Silently filtering out only the broken rows would hide the
fact that something is actually wrong with the data source, and a
partially-clean batch is a worse trap than an obviously failed one.

## Running it for real (once you have OANDA credentials)

```bash
export MARKET_DATA_PROVIDER=oanda
export MARKET_DATA_API_KEY=your_oanda_practice_api_token
export MARKET_DATA_ACCOUNT_ID=your_oanda_account_id

python -m app.data_engine.ingest --symbol EUR/USD --timeframe 1h \
    --start 2023-01-01 --end 2024-01-01
```

Then confirm it's queryable:

```bash
curl "http://localhost:8000/market-data/candles?symbol=EUR/USD&timeframe=1h&limit=10"
```

## What was tested in this sandbox vs. what needs your real setup

This sandbox has no network access to OANDA and couldn't install a
local PostgreSQL server, so:

- **Tested for real here:** normalization and validation logic, against
  a realistic synthetic EUR/USD candle set (including a deliberate OHLC
  violation, a duplicate timestamp, and a genuine weekend gap) — 14/14
  tests passing. The app boots with the new `/market-data/candles`
  route registered.
- **Needs your real environment:** the actual OANDA fetch (needs
  network + real API credentials) and the storage upsert (needs a real
  Postgres instance — you already have this pattern working via
  Supabase for Con Z, same idea applies here).

## Next: Phase 2

Once real EUR/USD candles are sitting in `market_candles`, Phase 2
computes the 10/50 SMAs and other indicators on top of that stored
data — no new data-fetching logic needed, just reading what Phase 1
already stored.
