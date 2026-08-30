# Phase 9 — Market-Structure Breakout Research

**REAL HISTORICAL RESULTS.** Same dataset used since Phase 4.5:
`ejtraderLabs/historical-data`, EUR/USD 1H, 2012-11-16 → 2022-03-04,
57,600 candles, same 70/15/15 chronological split.

**Reminder, stated once here and true throughout:** the out-of-sample
period has already been seen by this project since Phase 4.5. Every
result on it below is **research evidence**, not fresh confirmation
evidence. Fresh-data confirmation (attempted and not obtained in Phase
8.1) remains a future requirement before any promising result here
could mean more than it currently does.

## Hypothesis

*When price breaks decisively beyond a well-defined recent range, the
breakout may contain enough directional persistence to produce
positive expectancy after realistic trading costs.*

**Structurally distinct from every prior hypothesis:** entry is driven
by a lagged price-structure threshold (a break of prior range), not a
moving-average relationship (SMA crossover), an oscillator level (RSI
filtering), a range-position mean-reversion signal (H1), or a
volatility-compression signal (H2).

## Why this isn't expressed via Phase 7's `Condition` system

Phase 7 documented that `Condition` can only compare fields within a
*single candle's own* feature snapshot — it has no way to express
"this candle vs. a lagged prior value." A real breakout rule needs
exactly that (today's close vs. the high/low of the *preceding* N
candles, excluding today). Rather than force a declarative system into
a shape it wasn't built for, this strategy is bespoke code
(`app/strategy_engine/breakout.py`) — the same architectural choice
Phase 3 made for the SMA crossover, which likewise isn't expressed via
`Condition`. A `Hypothesis` object is still registered for
documentation/versioning purposes, with the real parameters recorded
in its `risk_conditions` dict and the entry logic honestly left as
empty `RuleSet`s rather than a misleading placeholder.

## Entry rule (exact)

`prior_high[t]` = max(high) over candles `[t-lookback, t-1]` —
**excluding candle t's own high.** `prior_low[t]` is the mirror using
lows. Computed via `pandas.Series.shift(1)` **before** the rolling
max/min — the same technique already used correctly for ATR's
previous-close reference in `technical_engine/indicators.py`.

- **LONG** when close breaks above `prior_high` (fires once, on the
  transition candle — never repeated while price remains extended)
- **SHORT** when close breaks below `prior_low`, the mirror

## Exit rule (fixed, not swept)

Reuses Phase 6's `ExitConfig` **unmodified**: ATR stop (2.0×, frozen
at entry — not recalculated) OR max holding (100 candles) OR an
opposite-direction breakout, whichever triggers first. No new exit
infrastructure was written for this phase.

## Parameter selection — justified against the existing codebase

**Lookback neighborhood: 20 / 40 / 60 candles.** 20 is not an
arbitrary starting point — it's the *same* window already used for
`recent_high`/`recent_low` throughout Phases 5, 7, and 8
(`RECENT_HIGH_LOW_WINDOW` in `technical_engine/features.py`). Using it
as breakout's central value keeps this strategy comparable to prior
work rather than introducing an unrelated number. 40/60 are 2x/3x
multiples — also loosely consistent with classic Donchian-channel
breakout conventions (20/55-candle lookbacks in the "Turtle Trading"
system), an independent sanity check.

**ATR stop multiple: 2.0** — reuses Phase 6's exact, already-tested
`atr_stop_2x` value rather than introducing a new untested number.

**Max holding: 100 candles (~4.2 days)** — roughly half of Phase 6's
200-candle cap, which was found to *never bind* for the SMA
crossover's mean-reversion-flavored trades (median holding was 36
hours). Breakout trades are hypothesized to resolve faster than a slow
crossover reversal, so a tighter but still generous safety net is
reasoned, not arbitrary. This is a safety net, not the primary exit —
the ATR stop is expected to do most of the work.

## Data & periods

Same dataset, same 70/15/15 chronological development/validation/
out-of-sample split used since Phase 4.5. Dataset SHA256 recorded in
`research/results/phase_9_breakout_results.json`.

## Results — all three lookbacks, all three cost tiers, all three periods

### lookback = 20

| Period | Trades | Win Rate | Return (LOW/BASE/HIGH) | PF (LOW/BASE/HIGH) |
|---|---|---|---|---|
| development | 1,139 | 26.9% | -0.318 / -0.373 / -0.500 | 0.878 / 0.859 / 0.816 |
| validation | 219 | 37.0% | +0.124 / +0.113 / +0.088 | 1.350 / 1.315 / 1.237 |
| out_of_sample | 261 | 24.9% | -0.077 / -0.090 / -0.119 | 0.831 / 0.807 / 0.755 |

### lookback = 40

| Period | Trades | Win Rate | Return (LOW/BASE/HIGH) | PF (LOW/BASE/HIGH) |
|---|---|---|---|---|
| development | 757 | 23.6% | -0.182 / -0.217 / -0.295 | 0.905 / 0.889 / 0.852 |
| validation | 149 | 31.5% | +0.093 / +0.086 / +0.070 | 1.353 / 1.321 / 1.251 |
| out_of_sample | 161 | 26.1% | +0.012 / +0.004 / -0.013 | 1.040 / 1.015 / 0.959 |

### lookback = 60

| Period | Trades | Win Rate | Return (LOW/BASE/HIGH) | PF (LOW/BASE/HIGH) |
|---|---|---|---|---|
| development | 591 | 22.5% | -0.265 / -0.291 / -0.351 | 0.837 / 0.823 / 0.791 |
| validation | 122 | 27.9% | +0.028 / +0.023 / +0.010 | 1.109 / 1.086 / 1.036 |
| out_of_sample | 142 | 22.5% | -0.039 / -0.045 / -0.059 | 0.869 / 0.850 / 0.808 |

**No configuration is being declared a winner.** All three are
reported in full, including the two (lookback 40 and 60) that show a
brief near-breakeven or slightly-positive moment in one tier/period.

## Verdict (BASE cost, Phase 7 verdict engine, unmodified)

**All three lookbacks: `REJECTED`.** Development profit factor is
below 1.0 for every configuration (0.859 / 0.889 / 0.823) — the
verdict engine's rule triggers immediately regardless of what
validation or out-of-sample show.

## The structurally interesting finding — payoff shape, not win rate

Win rates are low across the board (22-37%) — on their own this reads
as a weak strategy. But **payoff ratio tells a different, more
nuanced story**: consistently 2.2-2.9 across every lookback and
period — wins are **2-3x the size of losses**, the opposite profile
from H1 (mean reversion), whose payoff ratio was ~0.5 (losses twice
the size of wins). This is exactly the shape a genuine trend-following
breakout mechanism is supposed to have: many small stop-outs,
occasional large trend-following wins.

**Breakeven win rate given this payoff ratio is only ~26-31%** — much
lower than the naive 50% intuition. Development and out-of-sample win
rates mostly sit at or slightly below that breakeven bar; validation's
win rates (28-37%) sit comfortably above it, which is exactly why
validation is the only consistently profitable period across all
three lookbacks.

**This validation-period favorability is not unique to breakout** — it
echoes a pattern already seen in Phase 4.5 (SMA baseline) and Phase 8
(H1): the validation slice (which contains the 2020 COVID volatility
spike) tends to look better than development or out-of-sample across
*multiple, structurally unrelated* strategies. That's worth naming
directly: a single unusual macro period dominating one chronological
slice can make many different approaches look temporarily better
there, which is a reason for *extra* caution about validation-period
results specifically, not a reason to trust them more.

## Drawdown, consecutive losses, holding time (lookback=20, BASE cost)

| Period | Max DD% | Max Consec. Losses | Median Holding |
|---|---|---|---|
| development | 44.3% | 14 | 24.0 hrs |
| validation | 6.0% | 9 | 26.0 hrs |
| out_of_sample | 13.9% | 17 | 21.0 hrs |

Development's 44% drawdown is severe. Full breakdown for all three
lookbacks and all cost tiers is in
`research/results/phase_9_breakout_results.json`.

## Lookahead protection — tests A through E

All five required tests implemented and passing, in
`tests/test_breakout.py` and `tests/test_breakout_engine_integration.py`:

- **Test A** (`test_A_current_candle_excluded_from_its_own_threshold`):
  a candle with an extreme high of its own does not affect its own
  breakout threshold — hand-verified with a constructed extreme value.
- **Test B** (`test_B_future_price_spike_does_not_alter_earlier_signals`):
  appending an absurd future candle leaves every earlier signal
  byte-identical.
- **Test C** (`test_C_out_of_order_and_duplicate_timestamps_rejected_upstream`):
  proves reuse of Phase 1's normalizer, not a reimplementation.
- **Test D** (`test_D_execution_happens_at_next_candle_open_not_signal_candle`):
  entry price/timestamp verified to be candle T+1's open, not T's close.
- **Test E** (`test_E_signal_on_final_candle_never_executes`): a
  breakout signal on the last available candle produces zero trades.

## The Phase 6-mistake regression test (spec section 11)

`test_breakout_signals_actually_reach_the_backtester` proves real
breakout signals produce a real trade, and a control all-WAIT signal
list produces zero trades and a different result — directly
demonstrating the engine genuinely depends on the signals it's given,
not some other implicit path. The exact bug class Phase 6 found (an
experiment silently recomputing an unfiltered baseline underneath a
filtered signal list) is structurally impossible to reproduce here,
since this phase never calls a "recompute the baseline" helper at all
— `run_one()` always threads `signals` through
`simulate_trades_with_exit_rules` directly.

## Tests: 254/254 passing

239 from Phases 1-8.1 unchanged, 15 new (10 in `test_breakout.py`,
4 in `test_breakout_engine_integration.py`, 1 extending the research
security boundary suite to cover `breakout.py` explicitly).

## Bugs discovered

One, in my own new security test — a leftover variable name
(`FORBIDDEN_TOKENS`) that didn't match the actual two-list structure
already defined in the existing test file. Caught immediately by
running the test (`NameError`), fixed, rerun clean. Not a bug in
`breakout.py` itself — confirmed separately via direct grep before
writing the test.

## Security boundary

Extended `test_research_security_boundary.py` with an explicit scan of
`breakout.py` (previously outside the existing scan's directory
scope) for execution and broker tokens — passes cleanly. Application
boot and full route registration verified unaffected.

## Statistical interpretation — observed vs. interpretation vs. hypothesis for future research

**Observed:** all three lookbacks show development profit factor below
1.0, a consistent 2.2-2.9 payoff ratio, and validation-period-specific
profitability across all three configurations.

**Interpretation:** the underlying win rate is not high enough to
clear the (admittedly favorable) breakeven bar in two of three
periods. The validation-only profitability is more likely a property
of that one chronological slice (an unusually volatile, trending
period) than evidence of a real edge — the same slice has now favored
multiple structurally different strategies across this project.

**Hypothesis for future research (not tested, not a claim):** a
breakout mechanism paired with a regime filter (e.g., only trading
breakouts during Phase 5's `HIGH_VOLATILITY` or `TRENDING_*` regimes,
rather than unconditionally) might concentrate trades in the
conditions where this payoff shape is actually favorable — untested,
recorded here as a lead for later, not acted on in this phase.

## Limitations

- Only EUR/USD 1H tested — no claim about other instruments or timeframes.
- The validation-period favorability pattern noted above is itself
  only an observation across a handful of strategies in one project,
  not a rigorously established general finding.
- Exit parameters (ATR multiple, max holding) were fixed, not swept —
  by design, per the spec's instruction not to optimize this phase,
  but it does mean the exit mechanism itself was not stress-tested the
  way the entry lookback was.

## What would be required for future confirmation

Same standard as H1 (Phase 8.1): genuinely fresh, clearly-licensed
data extending past 2022-03-04, tested exactly once on an unmodified
rule. None of the three lookbacks tested here are close enough to
justify that effort on their own merits — this is recorded as a
requirement for *any* future promising result from this project, not
a specific next step for breakout.

## Verdict — genuinely rejected, or just uninteresting?

**Genuinely rejected**, not a borderline case like H1. Development
profit factor is clearly below 1.0 for all three configurations, with
real, structural reasoning (a payoff ratio that doesn't quite clear
the breakeven bar outside one favorable chronological slice) — not a
razor's-edge result requiring the kind of dedicated robustness review
Phase 8.1 gave H1.

## Recommended next step

Not decided automatically, per the instructions for this phase.
**One recommendation:** the regime-filtered breakout hypothesis noted
above (trading breakouts only during Phase 5's high-volatility/trending
regimes) is the most concrete, evidence-motivated lead from this
phase — testing it would directly follow from what was actually
observed here, rather than starting a new unrelated strategy family.
Deferred to you.
