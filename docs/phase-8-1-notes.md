# Phase 8.1 — H1 Robustness & Statistical Validation

**REAL HISTORICAL RESULTS, DIAGNOSTIC ONLY.** No fresh data was
obtained (see below), so per the pre-registered rule, **the official
Phase 8 verdict for H1 remains exactly `OUT_OF_SAMPLE_FAILED`,
unchanged.** Everything in this document is diagnostic analysis of
already-seen data — informative, never grounds to override the
recorded verdict.

## Fresh-data availability

Checked five real sources before concluding:

| Source | Result |
|---|---|
| `ejtraderLabs/historical-data` (original dataset) | Ends exactly 2022-03-04 |
| `komo135/forex-historical-data` | Downloaded, diffed against the original — byte-identical mirror, no extension |
| `FX-Data/FX-Data-EURUSD-DS` | Release branches stop at 2022, appears unmaintained since |
| HuggingFace `ATB/AI-trade-bot-demo` (claims 2018–Feb 2023) | Space shows a runtime error; single ad-hoc file upload, no clear license or maintained provenance |
| Kaggle `godfrenam/eurusd-15min-2023-2025` | Requires Kaggle API authentication not available in this environment |

**No genuinely fresh, easily-obtainable, clearly-licensed EUR/USD 1H
data extending past 2022-03-04 was found.** This is recorded plainly,
per the pre-registered rule for exactly this outcome.

## H1's rule — reused, not retyped

`app/research/statistics_analysis.py` and this phase's script both
import `build_h1_range_extreme_reversion()` directly from Phase 8's
own script rather than reconstructing the rule from the written
description — this guarantees the H1 tested here is byte-identical to
the one already on record, not a manual transcription that could
silently drift. `verdict.py`, `baseline.py`, and the recorded Phase 8
experiment result were not touched.

## 1. Transaction cost sensitivity — H1 unmodified, all periods

| Cost Tier | Development PF | Validation PF | Out-of-Sample PF |
|---|---|---|---|
| LOW | 1.163 | 1.140 | **1.040** |
| BASE | 1.134 | 1.101 | **1.000** |
| HIGH | 1.069 | 1.015 | **0.911** |

**H1's already-thin out-of-sample edge does not survive HIGH costs.**
At LOW cost it's marginally profitable; at BASE it's exactly
break-even; at HIGH it's a loss. A result this sensitive to the exact
cost assumption is not a robust edge — it's evidence the underlying
signal, if it exists at all, is too weak to survive realistic
uncertainty in trading costs.

## 2. Parameter neighborhood (one parameter at a time, BASE cost)

**Distance threshold** (atr_ceiling fixed at 0.0015):

| Value | Development PF | Validation PF | Out-of-Sample PF |
|---|---|---|---|
| 0.0004 | 1.237 | 1.189 | 1.036 |
| **0.0005 (original)** | 1.134 | 1.101 | **1.000** |
| 0.0006 | 1.116 | 1.136 | 0.880 |

**ATR ceiling** (distance fixed at 0.0005):

| Value | Development PF | Validation PF | Out-of-Sample PF |
|---|---|---|---|
| 0.0012 | 1.209 | 1.001 | 0.902 |
| **0.0015 (original)** | 1.134 | 1.101 | **1.000** |
| 0.0018 | 1.187 | 0.976 | 0.927 |

**This is the most important finding in this phase, and it does not
favor H1.** On the ATR-ceiling axis, out-of-sample profit factor forms
a **local peak exactly at the originally-chosen value** (0.902 → 1.000
→ 0.927) — worse on both neighboring sides. That specific shape —
a lone spike at the exact value that happened to be chosen, surrounded
by worse results — is close to a textbook signature of a threshold
that fits a peculiarity of this one dataset rather than a real,
generalizable pattern. It doesn't matter that 0.0015 was originally
chosen only for testability (documented in Phase 8), not for
performance — real out-of-sample data can still expose a threshold as
fragile regardless of why it was picked. The distance-threshold axis
degrades more smoothly (1.036 → 1.000 → 0.880), which is somewhat less
alarming on its own, but combined with the ATR-ceiling result, the
overall parameter neighborhood does not look stable.

## 3. Statistical analysis (H1, out-of-sample, BASE cost, 253 trades)

- **Average win:** $26.43 | **Average loss:** -$52.88 | **Payoff
  ratio:** 0.4999 (losses are roughly **twice** the size of wins)
- **Largest win:** $122.00 | **Largest loss:** -$375.10
- **Breakeven win rate** (given this payoff ratio): **66.67%**
- **Actual win rate:** 66.40% — fractionally *below* the breakeven
  rate. This is exactly why profit factor landed at 1.000: the win
  rate sits right at the mathematical edge of what the payoff shape
  requires, not by coincidence.
- **Wilson 95% confidence interval on win rate:** (60.4%, 71.9%) —
  **this interval contains the 66.67% breakeven rate.** We cannot
  statistically distinguish H1's actual win rate from the exact rate
  needed to break even.
- **Bootstrap 95% confidence interval on total out-of-sample P&L:**
  (-$1,714, +$1,597) — **this interval contains zero.** We cannot
  statistically distinguish H1's total out-of-sample result from no
  edge at all. (Bootstrap limitation: trades are resampled as if
  independent, which real consecutive trades are not exactly — see
  `statistics_analysis.py` docstring for the full caveat.)

**Answering the original question plainly: the ~62-66% win rate is
not, on its own, meaningful.** It only looks impressive without the
payoff ratio next to it. With the payoff ratio included, that same win
rate is revealed to sit almost exactly on the knife-edge of breakeven
— which is a very different, much less exciting story than "66% win
rate" suggests in isolation.

## 4. Regime dependence (H1, out-of-sample, 253 trades)

| Regime | Trades | Win Rate | Net P&L |
|---|---|---|---|
| RANGING | 177 (70% of all trades) | 62.7% | **-$76.40** |
| TRENDING_UP | 42 | 81.0% | **+$190.30** |
| TRENDING_DOWN | 32 | 68.8% | -$100.00 |
| UNKNOWN | 2 | 50.0% | -$15.10 |

**H1's near-breakeven overall result is not broad-based.** The
majority of trades (RANGING, 70% of the sample) are net **negative**
despite a respectable-looking 62.7% win rate — the same payoff-ratio
effect as above. The positive contribution comes almost entirely from
a 42-trade TRENDING_UP subset. A strategy whose only positive
contribution comes from one-sixth of its trades, while the majority
bucket loses money, is a materially weaker and more fragile story than
"consistently near breakeven across the board."

## SUCCESS / FAILURE / INCONCLUSIVE — applying the pre-registered criteria exactly

Per the approved specification: **SUCCESS requires genuinely fresh
confirmation data**, which was not obtained. That alone means SUCCESS
is not available as an outcome here, regardless of any other finding.

Independent of that, the diagnostic evidence itself would not have
supported SUCCESS even if fresh data had been available:
- Parameter neighborhood is **not stable** (ATR-ceiling local-peak pattern)
- Edge does **not survive HIGH cost** (falls to 0.911)
- Statistical checks **cannot distinguish the result from chance**
  (breakeven rate inside the Wilson CI; zero inside the bootstrap CI)
- Result is **not broad-based** (concentrated in a 42-trade regime subset)

**Outcome: INCONCLUSIVE**, per the pre-registered criteria — driven
primarily by the absence of fresh data, and independently corroborated
by every diagnostic check available. **The official H1 verdict
remains `OUT_OF_SAMPLE_FAILED`, unchanged.** The diagnostics gathered
here do not contradict that verdict — if anything, they explain in
more detail *why* the profit-factor-exactly-1.000 headline was never
as promising as it first looked.

## What this phase actually accomplished

The Phase 8 report called H1 "the strongest candidate for dedicated
follow-up research... not because the verdict says so, but because
the diagnostics raised no red flags." That framing was accurate at the
time — Phase 8's own automated overfitting diagnostics genuinely
raised no flags. **This phase found the problems those diagnostics
weren't built to catch**: payoff-ratio-adjusted win rate significance,
parameter-neighborhood stability, and regime concentration. That's not
a contradiction — it's why this dedicated robustness phase existed at
all, and it's a legitimate example of research doing its job: a result
that survived one layer of scrutiny did not survive a deeper one.

## Bugs discovered

One, in this phase's own test suite (not in `statistics_analysis.py`
itself): a test assumed two different random seeds must always produce
different confidence-interval *boundary values*. Investigated before
accepting the test failure at face value — confirmed the underlying
resampled distributions genuinely differ per seed, but with a small
number of distinct input P&L values, the resampled sums only take a
small number of distinct discrete values, so the 2.5th/97.5th
percentile boundaries can coincidentally land on the same value even
across different seeds. Not a bug in the bootstrap implementation —
fixed the test to check the real invariant with a larger, more varied
sample, and documented the small-sample discreteness property in
`statistics_analysis.py` itself, since it's a genuine thing worth
knowing about the method, not just an artifact of one test.

## Files created

- `app/research/statistics_analysis.py`
- `backend/scripts/run_phase8_1_h1_robustness.py`
- `tests/test_statistics_analysis.py`
- `research/results/phase_8_1_h1_robustness.json`
- This document

## Files modified

None. `verdict.py`, `baseline.py`, H1's original hypothesis definition
(reused via import), and the Phase 8 experiment registry are all
untouched.

## Tests: 239/239 passing

226 from Phases 1-8 unchanged, 13 new (payoff stats, breakeven win
rate, Wilson interval against known reference values, bootstrap
interval determinism and the discreteness property above).

## Security

Reused Phase 7's existing security-boundary test suite, which already
scans all of `app/research/*.py` — new files pass cleanly: no
eval/exec, no broker/execution imports, no credentials.

## Limitations

- Bootstrap CI treats trades as independent draws — a standard
  simplification, documented, not a claim of full statistical rigor.
- Only 95% confidence level is implemented for both interval methods.
- Regime dependence was checked only for H1's out-of-sample trades,
  not development/validation — a deliberate scope limit to keep this
  phase focused, not an oversight.
- This diagnostic analysis, however thorough, remains diagnostic. It
  cannot substitute for genuinely fresh out-of-sample data, which
  remains the single piece of evidence that could actually move H1's
  status.

## Recommended next step

Not decided automatically, per the instructions for this phase. Two
honest options: (1) treat H1 as closed — the evidence base here is
now unusually thorough for a rejected/inconclusive result, and further
work on it has diminishing returns — or (2) if a legitimately-licensed
fresh dataset becomes available later (e.g. a paid or properly
authenticated source), H1 could be given one single, final,
un-iterated confirmation test against it. Deferred to you.
