# Phase 8 — Structurally Different Strategy Research

**REAL HISTORICAL RESULTS.** Same dataset as every phase since 4.5:
`ejtraderLabs/historical-data`, EUR/USD 1H, 2012-11-16 → 2022-03-04,
57,600 candles, same 70/15/15 chronological split, same BASE_COST
config ($10,000 balance, 10,000-unit position, 1 pip spread, 0.2 pip
slippage) used since Phase 4.5.

## Why this phase, and why now

Phases 4.5-7 established that SMA10/50 crossover — and five filters/
exits layered on top of it — show no robust edge. Rather than continue
tweaking the same moving-average mechanism, this phase tests two
hypotheses built on genuinely different mechanisms, using Phase 7's
rule language and evidence-based verdict engine.

## Pre-registration

Both hypotheses, and their exact thresholds, were fixed in
`scripts/run_phase8_hypotheses.py` before the script was ever run
against validation or out-of-sample data. Threshold values were
chosen using only the FULL dataset's overall distribution (to confirm
each rule would fire often enough to be testable at all — see the
sanity-check step below) — never chosen or adjusted based on
period-specific results.

**A rule-language constraint shaped both designs:** Phase 7's
`Condition` only supports `field OP literal` or `field OP field` — no
scaling multiplier (e.g. "distance_from_low < 0.15 × rolling_range"
isn't directly expressible). Both hypotheses below were designed
around this real constraint rather than extending the schema
mid-experiment, which would have meant modifying a just-built,
security-reviewed model to chase a specific idea.

**Sanity check before finalizing thresholds:** counted how many
candles (not yet trades) satisfied each candidate threshold across the
full dataset, to avoid Phase 7's "zero trades" trap (the breakout
hypothesis that could structurally never fire). `distance_from_low/high
< 0.0005` yields ~3,300/3,160 qualifying candles; `rolling_range <
0.0030` yields ~1,050/1,620 — both comfortably testable, neither
vanishingly rare nor so common the condition is nearly always true.

## H1 — Range-Extreme Mean Reversion

**Rule:** LONG when `distance_from_low < 0.0005` AND `atr_percent <
0.0015` (near the 20-candle low, calm volatility). SHORT is the exact
mirror at the recent high.

**Rationale:** range position (distance from the recent high/low) is
a structurally different signal from RSI or an SMA relationship — it
measures where price sits within its own recent trading range. The
volatility filter specifically excludes breakout-like conditions,
where a range extreme is more likely to continue than revert.

**Results:**

| Period | Trades | Win Rate | Net P&L | Return | Profit Factor |
|---|---|---|---|---|---|
| development | 681 | 62.6% | +$2,308.30 | +23.08% | 1.134 |
| validation | 199 | 61.8% | +$375.20 | +3.75% | 1.101 |
| out_of_sample | 253 | 66.4% | **-$1.20** | -0.001% | **1.000** |

**Verdict: `OUT_OF_SAMPLE_FAILED`** (the deterministic verdict engine's
actual output — reported exactly, not softened).

**This deserves more nuance than the label alone conveys.** The
verdict engine's rule is: development profit factor >1.0 AND
out-of-sample profit factor ≤1.0 → `OUT_OF_SAMPLE_FAILED`. Here,
out-of-sample profit factor landed at **exactly 1.000** — not below
it, not a collapse, just precisely break-even. `overfitting_diagnostics`
confirms: `"any_flag_raised": false` — no low-trade-count flag, no
strong-development-then-failure pattern. Win rate stayed remarkably
stable across all three periods (62.6% → 61.8% → 66.4%) — nothing
else tested in this entire project has held that consistent across
periods. The out-of-sample result is genuinely **flat**, not a
collapse: -$1.20 on a $10,000 account over 253 trades.

**Reported plainly: this is the system's verdict, and it's correct by
its own stated rule** — a hard `>1.0` threshold treats an exact tie as
failure, by design, and this hypothesis landed exactly on that line.
That's not a reason to override the verdict to make it look better —
the whole point of this engine is that a hard rule beats a
comfortable-feeling exception. But it IS worth naming as a genuine
limitation of a binary threshold verdict system, exposed by a real
near-boundary case, the same way Phase 7 named the breakout rule's
limitation when it hit one. **This is the strongest candidate for
dedicated follow-up research of anything tested across Phases 4.5-8** —
not because the verdict says so, but because the diagnostics raised no
red flags and the pattern held steady across three independent slices
of data.

## H2 — Volatility Squeeze Breakout

**Rule:** LONG when `rolling_range < 0.0030` (a compressed 20-candle
range) AND `sma_50_slope > 0`. SHORT is the mirror with negative slope.

**Rationale:** range compression is a volatility-structure signal,
distinct from momentum or a moving-average relationship. The
hypothesis: a squeeze resolves in the direction of the existing trend.

**Results:**

| Period | Trades | Win Rate | Net P&L | Return | Profit Factor |
|---|---|---|---|---|---|
| development | 91 | 38.5% | -$2,032.60 | -20.33% | 0.677 |
| validation | 46 | 54.3% | -$582.50 | -5.83% | 0.661 |
| out_of_sample | 47 | 34.0% | -$51.70 | -0.52% | 0.971 |

**Verdict: `REJECTED`** — profit factor below 1.0 in every period,
including development. Unusually, out-of-sample was the *least* bad
period (0.971, nearly breakeven) rather than a further decline from
development — an inconsistent pattern that doesn't support the
underlying mechanism, not a partial success.

## What this phase changes about the project's overall picture

Six hypotheses across Phases 6-8 have now been tested against real
data with genuine out-of-sample discipline. Five were clearly
rejected or failed out-of-sample. **One (H1) is the first result in
this entire project that didn't collapse out-of-sample** — it landed
exactly on the verdict engine's pass/fail boundary instead. That's a
meaningfully different outcome from "this doesn't work," even though
the formal verdict and Phase 6-7's other hypotheses use the same
words superficially.

## Security & regression

Both hypotheses went through the existing Phase 7 security-reviewed
path unchanged — `Condition`'s closed field/operator allowlist, the
deterministic rule evaluator, the unmodified Phase 4/6 backtesting
engine. No new code was added to `app/research/`'s core modules; this
phase only adds a new script and two hypothesis definitions using the
existing, already-tested interfaces.

## Tests

No new test files this phase — H1/H2 are hypothesis *data*, evaluated
through Phase 7's already-tested `Condition`/`RuleSet`/
`run_research_experiment` machinery, not new code paths. The existing
226 tests continue to cover every piece of infrastructure this phase
exercises.

## Limitations

- **Rule-language scaling gap** (same as Phase 7's finding): no
  "field vs. K × field" comparison. Both hypotheses here were designed
  around this constraint using literal thresholds instead — a
  reasonable workaround, but a real, still-unaddressed gap for future
  hypotheses needing proportional comparisons (e.g., true Bollinger
  Band-style rules).
- **Verdict engine boundary sensitivity**, demonstrated directly by
  H1: an exact `profit_factor == 1.0` result is treated identically to
  a clear failure. A future refinement might report a boundary case
  differently from a clear miss, without weakening the underlying
  discipline against calling anything "promising" on weak evidence.
- Thresholds for both hypotheses were chosen for testability (enough
  occurrences to evaluate), not calibrated or optimized — consistent
  with every prior phase's threshold philosophy, but still worth
  restating: these are starting guesses, not derived values.

## Recommended next step

Not decided automatically. H1's exact-boundary result is the most
concrete lead this project has produced — a dedicated follow-up could
test it against an extended or different out-of-sample slice, or
examine whether a small tolerance band around the 1.0 threshold is
methodologically defensible (versus just moving the goalposts).
Deferred to you.
