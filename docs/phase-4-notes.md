# Phase 4 — Backtesting Engine (complete)

## What backtesting actually is

A backtest replays history candle-by-candle and asks: "if a trader
had mechanically followed this exact strategy, what would have
happened to their account?" It is an experiment, not a prediction. A
profitable backtest tells you the strategy *would have worked on this
specific stretch of the past* — it says nothing certain about the
future. See the final principle at the bottom of this document.

## How the engine works, step by step

```
Candles → technical_engine (SMA10/50) → strategy_engine (BUY/SELL/WAIT)
        → backtesting engine (this phase) → trades + equity curve + metrics
```

The engine itself is split into two layers:

- **`simulate_trades(candles, signals, config)`** — the pure
  simulation core. Takes candles and an *already-computed* signal
  list and just executes the mechanics: when to enter, when to exit,
  what it cost, what the account looked like afterward. Contains zero
  SMA or crossover logic.
- **`run_backtest(candles, config)`** — the real entrypoint. Calls
  `strategy_engine.run_crossover_strategy()` for signals, then hands
  them to `simulate_trades()`. This is the only place that connects
  to Phase 2/3 — nothing about SMA or crossover logic is duplicated
  here.

Splitting it this way is also what made rigorous testing possible:
most of the backtest tests construct exact `Signal` lists by hand
(the same technique Phase 3 used for `TechnicalFeature` lists), so
expected P&L, timing, and costs can all be verified by arithmetic,
not just trusted from the engine's own output.

## Execution timing — the most important design decision here

A crossover is detected on candle T using only data available at
candle T. But the strategy engine only *decides* what it would do
that hour — it can't have already traded during the candle it's still
forming. So: **a signal generated on candle T executes at candle
T+1's open price**, never at candle T's own close. This is the
`next_open` execution model, and it's the only one Phase 4
implements. A signal on the very last candle in a dataset has no T+1
to execute at — it's simply never executed, which is a documented gap
in the simulation, not a bug.

## Spread and slippage — the cost model

Every execution price is derived from the candle's mid price (its
open) plus real trading friction, always working against the trader:

- **Buying** (opening LONG, or closing/covering a SHORT):
  `execution_price = mid + spread/2 + slippage`
- **Selling** (opening SHORT, or closing a LONG):
  `execution_price = mid - spread/2 - slippage`

`gross_pnl` on a trade is computed from the two mid prices, as if
costs were zero. `net_pnl` uses the two actual execution prices.
`transaction_costs = gross_pnl - net_pnl` is reported on every trade
separately — costs are never silently folded into net P&L where they
can't be inspected.

**The default spread (0.00010, i.e. 1 pip) is an example/test value,
not a claim about real EUR/USD market conditions.** Real spread
varies by broker, time of day, and market volatility — anyone running
a serious experiment should set this explicitly and document why.

## Position sizing (Phase 4A — deliberately simple)

A fixed notional size per trade (default 10,000 units of the base
currency — loosely like a "mini lot"). This backtester does **not**
model margin, leverage, or lot-size constraints. Real risk-based
sizing (percent-of-account risk, volatility-adjusted size) is a later
phase, once `risk_engine` is wired in.

## Position model

At most one open position at a time. An opposite-direction signal
closes the current position and immediately opens the new one in the
opposite direction (a "reverse") — there is no flat/no-position state
in between, by design, matching how the crossover strategy itself
only ever signals BUY or SELL, never "close and wait."

## End-of-data handling

If a position is still open when the historical dataset runs out, it
is closed at the final candle's close price and tagged
`exit_reason="END_OF_DATA"` — never silently discarded, and never
confused with a real strategy-driven exit.

## Lookahead-bias protection, at this layer specifically

Phases 2 and 3 already proved SMA calculation and crossover detection
don't peek at future data. Phase 4 adds its own protection on top: the
candle-stepping loop only ever reads the *current* candle's own
open/close and state carried over from before it — nothing at index
i ever reads index i+1 or later. This is proven directly by
`test_backtest_lookahead.py`: running the engine on a truncated
dataset, then again with an absurd future price spike appended,
produces byte-identical trades and equity points for everything before
the truncation point.

## Metrics — the null-safety rule

Every ratio-based statistic (win rate, profit factor, average
win/loss, consecutive streaks) returns `None` — never a fabricated or
divide-by-zero value — when there isn't enough data to compute it
meaningfully. Zero trades means zero trades, not a 0% win rate or an
"infinite" profit factor.

## Worked example — SYNTHETIC DATA, NOT REAL MARKET PERFORMANCE

Run against `tests/fixtures/backtest_fixtures.py::trending_candles()`
— a hand-engineered price path (flat → sustained rise → flat →
sustained fall → flat) built purely to exercise the engine, with
default config ($1,000 starting balance, 10,000-unit position size,
1-pip spread, zero slippage):

```
3 trades | win rate 66.7% | net P&L +$141.00 | final balance $1,141.00
max drawdown $81.00 (7.08%)

#1 SHORT  entry 2024-01-10 08:00 @ 1.08995  exit 2024-01-10 13:00 @ 1.09085
   net P&L -$9.00  (reversed by an upward crossover)
#2 LONG   entry 2024-01-10 13:00 @ 1.09085  exit 2024-01-12 14:00 @ 1.09795
   net P&L +$71.00  (reversed by a downward crossover)
#3 SHORT  entry 2024-01-12 14:00 @ 1.09795  exit 2024-01-13 19:00 @ 1.09005
   net P&L +$79.00  (dataset ended — END_OF_DATA)
```

This is a hand-built synthetic price path designed to trigger clean,
well-separated crossovers for testing purposes. **It is not real
EUR/USD data and this result says nothing about how the strategy
would perform on real market history.**

## Whether real historical data was used

No. This sandbox has no network access to OANDA (documented already
in `docs/phase-1-notes.md`), so Phase 4 was built and tested entirely
against synthetic fixtures. The engine's input contract
(`list[Candle]`, already normalized/validated by Phase 1) is identical
whether the candles came from a fixture or from real OANDA data via
`app.data_engine.ingest` — running this same code against real stored
EUR/USD candles requires no engine changes, only real data in the
database.

## Known limitations (Phase 4 scope, not bugs)

- No stop-loss, take-profit, or time-based exit — the position simply
  holds until the opposite crossover, per the Phase 3 strategy
  definition. Risk controls are a later phase.
- Position sizing is a fixed notional amount, not risk-based.
- Spread and slippage are fixed constants, not time-varying or
  volume-dependent.
- No parameter optimization was performed or attempted — the strategy
  remains exactly SMA10/50 on EUR/USD 1H, deliberately, to avoid
  overfitting to this one historical stretch before there's even real
  data to test against.

## Regression check

**60/60 tests passing** — all 42 tests from Phases 1-3 unchanged, 18
new (11 engine-mechanics tests with hand-verified numbers, 5
metrics-null-safety and drawdown tests, 1 lookahead-bias regression
test, 1 security-boundary test confirming the backtesting module has
no code path to the broker adapter).

## Final principle

This backtester was not built to make the SMA10/50 strategy look
good. It was built to be trustworthy enough that, once real historical
EUR/USD data is available, whatever result it produces — profitable,
unprofitable, or inconclusive — can be accepted honestly.

## Next step

Not decided automatically, per the phase instructions. Options from
here include: running this exact engine against real OANDA data once
network/credentials are available, or reviewing this phase's design
before deciding what Phase 5 should be.
