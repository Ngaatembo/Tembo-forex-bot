# Phase 3 — Moving Average Crossover Strategy (complete)

## What the strategy actually does

At every candle, compare SMA10 to SMA50:

- If SMA10 was at-or-below SMA50 on the previous candle, and is now
  strictly above it → **BUY**
- If SMA10 was at-or-above SMA50 on the previous candle, and is now
  strictly below it → **SELL**
- Everything else → **WAIT** — including the entire warm-up period,
  and including every candle where the fast MA simply *stays* on
  whichever side it was already on

## The one design decision worth understanding clearly

A signal fires only on the exact candle where the lines cross — never
repeated on every candle afterward. If SMA10 stays above SMA50 for 40
candles straight, that's one `BUY` at the crossing candle and 39
`WAIT`s after it, not 40 `BUY`s. This is what makes it a *crossover*
strategy (an entry/exit trigger) rather than a *trend* indicator
(a continuous state) — Phase 4's backtester will open one trade on
that `BUY` and hold it until the matching `SELL`, not re-enter every
candle.

## Why exact equality doesn't fire a signal

If SMA10 lands exactly on SMA50, that's treated as still belonging to
the "at-or-below"/"at-or-above" side it's transitioning through — the
signal fires on the candle where it becomes *strictly* greater/less
than, not the equality candle itself. Tested explicitly in
`test_exact_equality_does_not_fire_a_signal_but_updates_state`.

## Why the very first post-warm-up candle can never signal

Detecting a crossover requires comparing today's SMA relationship to
*yesterday's*. The first candle with valid SMA10/SMA50 has no valid
"yesterday" to compare against (the prior candle was still in
warm-up), so it's always `WAIT` regardless of where the lines happen
to sit. Tested in `test_transition_out_of_warmup_never_fires_a_signal`.

## Architectural boundary

```
technical_engine  →  strategy_engine  →  (backtesting, Phase 4)
(SMA10/SMA50)         (BUY/SELL/WAIT)      (simulate trades on signals)
```

`strategy_engine` takes `TechnicalFeature` objects in and returns
`Signal` objects out. It never fetches data, never touches the
database, never calls a broker or an LLM, and — critically — **it does
not place any order, paper or live**. It only decides what the
strategy *would* do. Phase 4 is what actually simulates opening and
closing a position based on these signals, with realistic costs.

## API

`GET /strategy/crossover-signals?symbol=EUR/USD&timeframe=1h&limit=500`

Returns one signal per candle with `direction`, the SMA values it was
computed from, and a human-readable `reason`. No trade, order, or
P&L field exists in this response — that's Phase 4.

## Tests

12 new tests (9 crossover-logic tests using directly-constructed
`TechnicalFeature` sequences for precise control, 3 pipeline tests
proving candles → features → signals works end-to-end and stays
aligned). Full regression: **42/42 passing**, all 30 prior tests
unchanged.

## Known limitations (Phase 3 scope, not bugs)

- Only the single SMA10/50 crossover rule is implemented — no
  confirmation filters (volume, ADX, volatility), no multi-timeframe
  logic. Those are later, separate strategies per the architecture
  (breakout, mean-reversion, news+technical), not modifications to
  this one.
- No position sizing, stop-loss, or take-profit — a `Signal` says
  what direction the strategy would trade, not how much or with what
  risk controls. That's `risk_engine`, wired in at Phase 8.

## Next: Phase 4

Backtest these exact signals against the stored historical EUR/USD
data — realistic spread/slippage costs, win rate, drawdown, Sharpe
ratio, and a comparison against simple buy-and-hold. This is where we
find out whether this strategy has any measurable edge at all, on
real (not synthetic) data. Not started; waiting on your go-ahead.
