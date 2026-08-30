# Phase 2 — Technical Analysis Engine (complete)

## What SMA is, in plain terms

A Simple Moving Average smooths out price noise by averaging the last
N closing prices. SMA10 answers "what's the average price over the
last 10 hours?" — as each new hour arrives, the oldest hour drops off
and the new one joins, so the average "moves" forward in time.

## Why CLOSE prices, not open/high/low

Close is the standard choice for moving averages — it represents where
the market actually settled for that period, which is what most
strategies (including the crossover we're building toward) care about.
Using a different price silently would make results impossible to
compare against how everyone else defines an SMA.

## Warm-up periods — why the first several values are `null`

SMA10 needs 10 real closing prices to compute a real average. Before
candle #10, there simply aren't enough prices yet — so positions 0
through 8 are `null`, not a fabricated or zero-filled number. Same
logic for SMA50: the first 49 candles have no valid SMA50. This
matters a lot for backtesting later — a strategy must never be allowed
to "trade" during a warm-up period where its own indicators aren't
real yet.

## How lookahead bias is prevented

This is the single most important property of this whole module.
`calculate_sma()` uses a **trailing** window: the SMA at position T is
the average of positions `[T-9, T]` — it never looks at position
`T+1` or later. This is proven directly in
`test_indicators.py::test_sma_does_not_use_future_values`: the same
SMA value at the same index is produced whether or not a huge value is
appended to the *end* of the series afterward. If it changed, that
would mean a future value leaked backward — exactly the bug that makes
a backtest lie about how a strategy would have performed live.

## Input/output contract

**In:** a chronologically-ordered, duplicate-free list of `Candle`
objects (Phase 1's `normalize_candles()` already guarantees this for
anything that came through ingestion).

**Out:** a list of `TechnicalFeature` — one per input candle, same
order, same timestamps — each carrying `close`, `sma_10`, `sma_50`
(`None` during warm-up).

If the input isn't properly ordered, `calculate_features()` raises a
`ValueError` immediately rather than silently computing indicators
over misordered data. A wrong SMA that doesn't crash is far more
dangerous than one that does.

## Where this sits in the architecture

```
data_engine  →  technical_engine  →  (strategy_engine, Phase 3)
(candles)       (SMA10/SMA50)        (crossover BUY/SELL/WAIT)
```

The technical engine never fetches data, never touches OANDA or
PostgreSQL directly, and never emits a trading signal. It's pure math
on numbers it was handed. That boundary is what makes it trivially
testable (see `test_indicators.py` — no database, no network, no
mocking needed) and what keeps Phase 3's strategy logic swappable
later without touching this code at all.

## API

`GET /technical-analysis/sma?symbol=EUR/USD&timeframe=1h&limit=500`

Returns `sma_10`/`sma_50` per candle, `null` during warm-up. No
BUY/SELL/WAIT field exists in this response — that's Phase 3.

## Known limitations (Phase 2 scope, not bugs)

- Only SMA10/SMA50 are implemented; EMA/RSI/MACD/ATR/Bollinger/ADX are
  future phases, same module, same pattern
- The API endpoint reads directly from the market_candles table via
  the existing pattern from Phase 1's `/market-data/candles` — no new
  data-access abstraction was introduced, per the instruction not to
  duplicate existing modules

## Next: Phase 3

Phase 3 is the moving-average crossover strategy itself — detecting
when SMA10 crosses above/below SMA50 and turning that into a BUY/SELL/
WAIT signal. Not started; explicitly deferred per this phase's scope.
