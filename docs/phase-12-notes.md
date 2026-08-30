# Phase 12 — Regime-Conditional Strategy Research (Classification: C)

**REAL RESULTS.** Same dataset, same 70/15/15 split, same three cost tiers.

## What was tested and why

**Reused existing findings, not re-run (avoiding duplicate work):**
- Crossover baseline's regime breakdown — already fully computed in Phase 5.
- Breakout's regime-filtered performance — already fully answered in
  Phase 9.1 (12 combinations, all REJECTED, family SATURATED).

**New compute this phase:** H1 (Range-Extreme Mean Reversion) and all
three momentum hypotheses (T1 lookback=60, T2, T3) — none had been
regime-filtered before. `filter_signals_by_regime` (Phase 9.1) is
fully generic — no new filter logic was written, only applied to two
strategy families it hadn't touched before.

**Filters (pre-registered, fixed before any result seen):** 5 single
regimes (TRENDING_UP, TRENDING_DOWN, RANGING, HIGH_VOLATILITY,
LOW_VOLATILITY) + 1 combined (TRENDING_UP|TRENDING_DOWN|HIGH_VOLATILITY,
reused unmodified from Phase 9.1's own most-evidence-motivated
combination for breakout — not a new rationale invented for this phase).

**Predicted before running:** H1's own entry rule requires
`atr_percent < 0.0015`, structurally excluding `HIGH_VOLATILITY`
(`atr_percent > 0.0015`) — confirmed exactly: 0 trades.

## Results summary (BASE cost, out-of-sample)

| Strategy | Filter | OOS Trades | Retention | OOS PF | Verdict |
|---|---|---|---|---|---|
| H1 | TRENDING_UP | 58 | 22.9% | 1.592 | **REJECTED** |
| H1 | TRENDING_DOWN | 49 | 19.4% | 0.505 | REJECTED |
| H1 | RANGING | 181 | 71.5% | 0.819 | OUT_OF_SAMPLE_FAILED |
| H1 | HIGH_VOLATILITY | 0 | 0.0% | n/a | INCONCLUSIVE (predicted) |
| H1 | LOW_VOLATILITY | 0 | 0.0% | n/a | INCONCLUSIVE |
| H1 | TRENDING_OR_HIGH_VOL | 119 | 47.0% | 1.030 | OVERFIT_SUSPECTED |
| T1(60) | best (HIGH_VOLATILITY) | 45 | 9.2% | 1.239 | REJECTED |
| T2 | best (TRENDING_DOWN) | 38 | 35.2% | 1.211 | OVERFIT_SUSPECTED |
| T3 | best (HIGH_VOLATILITY) | 30 | 9.7% | 1.007 | REJECTED |

Full LOW/BASE/HIGH detail for all 4 strategies x 6 filters in
`research/results/phase_12_regime_conditional_results.json`.

## The one eye-catching number, examined and dismissed

H1's `TRENDING_UP` filter shows OOS profit factor 1.592 — but
**development is 0.900 and validation collapses to 0.220** (only 30
trades). This is exactly the "OOS improves but development
deteriorates" and "performance depends on one period" pattern flagged
in advance as something to watch for. **Not a lead — a small,
inconsistent sample producing a noisy OOS number.** Verdict correctly
computed `REJECTED` from the actual development failure, unaffected
by how good OOS alone looked.

## Pattern across all 24 filtered configurations

- **LOW_VOLATILITY is unusable as a filter for any strategy** — only
  0.6% of the dataset, every strategy retention drops to 0 trades.
- **HIGH_VOLATILITY retention is consistently tiny** (8-10% for
  momentum strategies) — too few trades to trust even when profit
  factor looks momentarily good (T3's 1.007 on 30 trades is
  essentially noise around breakeven, not a finding).
- **No filter reaches PROMISING for any strategy.** The closest
  approaches (`OVERFIT_SUSPECTED` for H1's combined filter and T2's
  TRENDING_DOWN) are explicitly the verdict engine's "inconsistent
  across periods" classification, not a pass.
- Filters that keep the most trades (RANGING, 62-80% retention) show
  the *worst* profit factors across every strategy — the safest,
  most-populated regime is also the least favorable one, consistently.

## Classification

**C — No meaningful regime edge.** None of the 24 regime-filtered
configurations across H1 and the three momentum hypotheses reach
`PROMISING`. High-retention filters underperform; the filters that
show a tempting profit factor do so on trade counts small enough
(9-23% retention) that the result is indistinguishable from sampling
noise, confirmed directly in H1's case by an inconsistent
development/validation picture underneath the appealing OOS number.

This is exploratory evidence from already-seen data, examined for
falsification rather than accepted at face value — consistent with
the anti-overfitting discipline this phase required. Nothing here
constitutes confirmatory evidence, since no fresh post-2022 dataset
exists to test against.

## Verdicts unchanged

No historical verdict was modified. H1 remains `OUT_OF_SAMPLE_FAILED`
(unfiltered), breakout remains `REJECTED`/`SATURATED` (Phase 9.1),
momentum remains `REJECTED` (Phase 11) — all exactly as recorded.

## Tests

4 new (regime-filter genericity across strategy families, empty-regime
handling, no-duplicate-trade invariant, low-trade-count safety). One
test-authoring gap found and fixed during writing: an "all regimes"
invariant test omitted `UNKNOWN` as a legitimate regime category
(candles where regime's own longer warm-up hasn't completed yet, even
though the strategy's own signal warm-up already has) — not a bug in
the filter itself, confirmed by investigation before changing the test.

**Full regression: 365/365** (361 unchanged + 4 new).

## Recommendation

Not decided automatically, per the instructions. Five structurally
distinct approaches (crossover, mean-reversion, breakout, momentum,
and now regime-conditioning on all of them) have now been tested
against this dataset with no candidate clearing `PROMISING`. That's a
strategic decision point, not a technical one — deferred to you.
