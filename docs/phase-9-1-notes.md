# Phase 9.1 — Regime-Filtered Breakout Validation

**REAL HISTORICAL RESULTS.** Same dataset, same 70/15/15 split used
since Phase 4.5. **Reminder:** the out-of-sample period has already
been seen by this project — every result below is research evidence,
not fresh confirmation.

## Hypothesis

*Market-structure breakouts may perform better when restricted to
market regimes where directional movement and volatility are more
favorable.*

## What was NOT changed

Phase 9's breakout strategy is unmodified and permanently recorded:
same lagged N-candle range breakout, same ATR-stop (2.0×) + max-hold
(100 candles) exit, same lookback neighborhood (20/40/60). This phase
adds exactly one thing on top: a filter that suppresses a breakout
signal unless the regime at the **signal candle** is in a pre-approved
set. `verdict.py`, `baseline.py`, and every Phase 9 result file are
untouched.

## Pre-registered filters (fixed before running, never adjusted after)

- **A — trending only:** `{TRENDING_UP, TRENDING_DOWN}`
- **B — high volatility only:** `{HIGH_VOLATILITY}`
- **C — trending or high volatility:** `{TRENDING_UP, TRENDING_DOWN, HIGH_VOLATILITY}`

## Signal-timing guarantee

The regime used for a filtering decision is read from the **same
index** as the signal itself — never a later candle's regime. Proven
directly: Tests A-C in `test_regime_filter.py`, plus
`test_section_11_no_filter_active_reproduces_phase9_baseline_exactly`
in the engine integration suite, which confirms an all-permissive
filter reproduces Phase 9's exact trades byte-for-byte.

## Results — every combination, BASE cost, verdict from the unmodified Phase 7 verdict engine

| Lookback | Filter | Dev PF | Val PF | OOS PF | Trade Retention (OOS) | Verdict |
|---|---|---|---|---|---|---|
| 20 | Unfiltered | 0.859 | 1.315 | 0.807 | 100% | REJECTED |
| 20 | A (trending) | 0.883 | 1.188 | 0.824 | 20.4% | REJECTED |
| 20 | B (high-vol) | 0.806 | 1.525 | 0.999 | **4.1%** | REJECTED |
| 20 | C (trending+high-vol) | 0.804 | 1.287 | 0.893 | 22.4% | REJECTED |
| 40 | Unfiltered | 0.889 | 1.321 | 1.015 | 100% | REJECTED |
| 40 | A (trending) | 0.872 | 1.208 | 0.826 | 24.2% | REJECTED |
| 40 | B (high-vol) | 0.867 | 1.208 | 1.008 | **4.2%** | REJECTED |
| 40 | C (trending+high-vol) | 0.863 | 1.235 | 0.889 | 26.6% | REJECTED |
| 60 | Unfiltered | 0.823 | 1.086 | 0.850 | 100% | REJECTED |
| 60 | A (trending) | 0.917 | 1.154 | 0.754 | 28.4% | REJECTED |
| 60 | B (high-vol) | 0.784 | 0.867 | 0.938 | **4.9%** | REJECTED |
| 60 | C (trending+high-vol) | 0.825 | 1.015 | 0.780 | 30.8% | REJECTED |

**Every one of the 12 combinations is `REJECTED`** — development
profit factor is below 1.0 in every single cell of this grid, at BASE
cost, with no exception. This is the cleanest, most unambiguous result
in this entire project: no filter, at any lookback, ever pushed
development performance above break-even. There is no borderline case
here requiring the kind of dedicated scrutiny Phase 8.1 gave H1.

## Trade retention — flagged explicitly, per spec section 7/13

**Filter B (high-volatility only) retains only 4.1-4.9% of original
trades in out-of-sample** (18-27 trades, down from 370-661). Even
where its OOS profit factor briefly approaches or crosses 1.0 (0.999,
1.008, 0.938), **this is not meaningful evidence at that sample
size** — a handful of trades either side of breakeven is well within
noise, not a signal. This is explicitly the situation the spec warned
about: *"A filter that improves profit factor by reducing 90% of
trades may not represent a meaningful improvement."* Filters A and C
retain more (16-31%) but their OOS profit factor still sits clearly
below 1.0 throughout.

## Cost sensitivity

Every combination degrades monotonically from LOW → BASE → HIGH cost,
consistent with every prior phase — no filter's already-negative
development result is rescued by a more favorable cost assumption, and
none needed to be checked at HIGH cost to find a reason for rejection
(development already failed at LOW cost too, in every case).

## Payoff ratio and drawdown (lookback=20, BASE cost — representative)

| Config | Dev Payoff Ratio | Dev Max DD% |
|---|---|---|
| Unfiltered | 2.337 | 44.3% |
| A (trending) | 2.979 | **15.5%** |
| B (high-vol) | 2.225 | 34.6% |
| C (trending+high-vol) | 2.408 | 44.2% |

**One observation worth naming without overselling it:** Filter A cuts
development drawdown sharply (44.3% → 15.5%) while modestly improving
payoff ratio — a similar pattern to Phase 8.1's ATR-stop finding for
H1 (a filter that helps risk metrics without fixing the underlying
profitability problem). This phase's scope is specifically about
whether regime filtering rescues profitability, not risk control — so
this is recorded as an observation for a possible future, separate
risk-focused question, not as evidence bearing on this phase's actual
verdict, which remains REJECTED regardless.

## Regime dependence — why filters didn't help

Consistent with Phase 5's original finding that breakout-style signals
cluster heavily outside pure trending regimes (a breakout, by
definition, tends to fire as price *enters* a new range, often still
classified RANGING or transitioning, not yet inside an established
TRENDING regime) — restricting to TRENDING/HIGH_VOLATILITY regimes
removes the majority of signals without concentrating the surviving
ones into a profitable subset. The filters didn't fail by bad luck;
they removed trades roughly proportionally to how the strategy's
edge (or lack of one) was already distributed.

## Statistical interpretation

**Evidence:** all 12 pre-registered configurations show development
profit factor below 1.0, with monotonic cost-sensitivity degradation
and no combination approaching a defensible edge, including small
retained-trade-count filters that briefly cross 1.0 by a margin far
too small to trust.

**Interpretation:** regime context, at least via these three
pre-registered filters, does not rescue the breakout strategy.
Filtering by regime trades away sample size for a marginal,
inconsistent, and cost-sensitive change in profit factor — never a
robust improvement.

**Future hypothesis (not tested here):** the drawdown-reduction effect
of Filter A, isolated as its own risk-focused question rather than a
profitability claim, echoing Phase 8.1's analogous ATR-stop finding
for H1. Recorded as a lead, not pursued in this phase.

## Lookahead & security tests — A through F, all passing

- **Test A/B/C** (`test_regime_filter.py`): signal-time-only regime
  use, future-price invariance, and regime-transition-after-signal
  cannot retroactively change an earlier decision — all hand-verified.
- **Test D/E** (`test_regime_filter_engine_integration.py`, real
  end-to-end): rejected signals produce zero trades; accepted signals
  still execute at next-open, unmodified from Phase 4/6.
- **Test F**: source-level scan of `regime_filter.py` for broker/
  execution/eval/exec tokens — clean.
- **Section 11 regression guarantee**
  (`test_section_11_no_filter_active_reproduces_phase9_baseline_exactly`):
  an all-permissive filter reproduces Phase 9's exact trades and
  summary, byte-for-byte — the direct defense against a Phase-6-style
  signal-discarding bug.

## Tests: 267/267 passing

254 from Phases 1-9 unchanged, 13 new (9 in `test_regime_filter.py`,
4 in `test_regime_filter_engine_integration.py`).

## Bugs discovered

One, caught by investigating rather than assuming: an early version of
`test_E_accepted_signal_still_executes_next_open` used an ATR-stop
exit config on a 6-candle scenario too short for ATR's own 13-candle
warm-up, producing 0 trades instead of the expected 1. Investigated
before accepting — confirmed this was **correct, already-documented
fail-closed behavior** in `engine_research.py` (a trade is skipped,
never crashed or opened unprotected, when an ATR-dependent exit can't
be computed) — not a regime-filter bug. Fixed by testing execution
timing with `BASELINE_EXIT` instead, which doesn't need ATR at all and
is what the test was actually trying to prove.

## Files created

- `app/strategy_engine/regime_filter.py`
- `backend/scripts/run_phase9_1_regime_filtered_breakout.py`
- `tests/test_regime_filter.py`, `test_regime_filter_engine_integration.py`
- `research/results/phase_9_1_regime_filtered_breakout.json`
- This document

## Files modified

None. Phase 9's strategy, exit config, lookback values, `verdict.py`,
`baseline.py`, and all prior research artifacts are untouched.

## Limitations

- Only three pre-registered filters were tested, per the spec's
  explicit anti-selection-bias instruction — this says nothing about
  other possible regime combinations, which were deliberately not
  explored.
- Filter B's small out-of-sample sample sizes (18-27 trades) mean its
  near-1.0 profit factors carry very little statistical weight — flagged
  above, not treated as a partial success anywhere in this document.
- The drawdown-reduction observation for Filter A is exactly that — an
  observation, not a tested hypothesis; no formal statistical
  validation (Wilson/bootstrap, as Phase 8.1 did for H1) was performed
  on it, since it falls outside this phase's actual research question.

## Final conclusion

**Regime filtering did not improve the breakout strategy.** Not "only
in development," not "inconclusive" — genuinely, cleanly rejected
across all three pre-registered filters, all three lookbacks, and all
three cost tiers, with development profit factor below 1.0 in every
one of the 12 tested combinations. This hypothesis family is closed,
per the spec's own instruction not to keep adding filters after a
disappointing result.

## Recommended next step

Not decided automatically, per the instructions for this phase.
**One recommendation:** given both of this project's two
structurally-different strategy families (mean reversion in H1,
breakout here) have now been thoroughly rejected or found
inconclusive even after dedicated robustness follow-ups, the more
valuable next question may be broader than another strategy variant —
worth a deliberate strategic discussion (as was done before Phase 8)
rather than a third incremental strategy-family experiment. Deferred
to you.
