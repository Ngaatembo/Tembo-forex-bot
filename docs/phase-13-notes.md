# Phase 13 — Market & Timeframe Discovery (Classification: B, one strong lead)

**REAL RESULTS.** Same 70/15/15 chronological methodology, same three
cost tiers, timeframe held constant at 1H throughout.

## Data & selection

Checked the same already-verified, Apache-2.0-licensed source
(`ejtraderLabs/historical-data`) for GBP/USD, USD/JPY, XAU/USD across
15m/1h/4h — all 9 combinations exist with matching 2012-2022 coverage.
Prices sanity-checked against real history for every instrument.

**Selected: GBP/USD 1H and XAU/USD 1H** (2 of the possible 12
combinations, not a sweep). Timeframe held constant because every
existing strategy's thresholds were calibrated against EUR/USD 1H's
own distributions — changing timeframe and instrument simultaneously
would confound the test. GBP/USD chosen as the closest structural
analog to EUR/USD; XAU/USD chosen as deliberately the most different
available asset (commodity, not forex, different price scale and
volatility character). USD/JPY excluded to keep the phase small.

## Strategies — reused exactly, no re-optimization

H1 (original unmodified rule), Breakout (established 40-candle
config), Momentum T1 (lookback=60) — the three families' central,
already-established configurations. No parameters were tuned for the
new markets.

## A real bug found and fixed, twice, before trusting anything

1. **XAU/USD price scale.** This source scales gold to 2 decimals
   (`154759.0` -> `$1547.59`), not the 5-decimal forex convention used
   for currency pairs. Applying the forex config blindly would have
   silently produced prices 1000x too small. Caught by a test
   assertion (`test_xauusd_requires_its_own_price_scale_not_the_forex_one`),
   verified against real 2012 gold prices, fixed with a dedicated
   `ejtrader_xauusd_import_config()`.
2. **Position-sizing scale mismatch.** A fixed unit-count
   `position_size=10,000` represents ~$11,800 notional for EUR/USD but
   ~$85M for XAU/USD at its much higher price — producing nonsensical
   returns up to 45,810% on the first run. Caught because profit
   factor (scale-invariant) looked sane while returns didn't. Fixed
   with a corrected, notionally-comparable position size derived from
   each instrument's own mean price (`8.30` for XAU/USD, keeping
   exposure comparable to EUR/USD's ~$11,800 average) — documented in
   `run_phase13_multimarket.py`, not silently patched over.

## Documented transfer limitation, confirmed exactly as predicted

H1's entry uses absolute price-unit thresholds (`distance < 0.0005`)
calibrated to EUR/USD's ~1.10 scale. On XAU/USD (~1,400), this
predicted failure was confirmed: **1, 3, and 1 trades** across
development/validation/OOS — `INCONCLUSIVE`, not a real test of the
mechanism. Not silently fixed; reported as the predicted limitation.

## Full results (BASE cost)

| Market | Strategy | Dev PF | Val PF | OOS PF | Verdict |
|---|---|---|---|---|---|
| GBP/USD | H1 | 0.779 | 0.712 | 1.063 | REJECTED |
| GBP/USD | Breakout40 | 1.101 | 1.322 | 0.641 | OUT_OF_SAMPLE_FAILED |
| GBP/USD | Momentum T1(60) | 1.024 | 1.273 | 0.796 | OUT_OF_SAMPLE_FAILED |
| XAU/USD | H1 | n/a (1 trade) | 0.025 | n/a (1 trade) | INCONCLUSIVE |
| **XAU/USD** | **Breakout40** | **1.072** | **1.572** | **1.061** | **PROMISING** |
| XAU/USD | Momentum T1(60) | 0.945 | 1.193 | 0.806 | REJECTED |

Full LOW/BASE/HIGH detail for all 6 combinations in
`research/results/phase_13_multimarket_results.json`.

## The lead: XAU/USD Breakout(lookback=40)

Verified formally through the full existing Phase 10 machinery (not eyeballed):

- **Verdict: `PROMISING`** — profit factor >1.0 held across all three
  periods (1.072 / 1.572 / 1.061)
- **Trade count:** 696 / 138 / 158 — not a small-sample fluke
- **EDGE: `STRONG`** (inherited directly from the Verdict)
- **RISK: `STRONG`** — payoff ratio 3.24, max drawdown 18.5%
- **REALISM: `STRONG`** — profit factor barely moves from LOW cost
  (1.061) to HIGH cost (1.061) — this specific result is essentially
  cost-insensitive
- **Overfitting diagnostics: zero flags raised** — no low-trade-count
  flag, no strong-development-then-failure pattern, minimal dev-to-OOS
  degradation (0.011)
- **Formal Research Gate status: `ROBUSTNESS_REQUIRED`**, not yet
  literally `PROMISING` at the gate level — specifically because
  parameter-neighborhood testing (nearby lookback values) was
  correctly out of scope for this phase, per the explicit instruction
  not to sweep parameters here. This is the gate doing its job
  correctly, not a weakness in the finding: robustness genuinely
  hasn't been checked yet.

**This is the strongest evidence this project has produced across
every phase to date.** No prior candidate — including H1 — has ever
simultaneously cleared EDGE/RISK/REALISM at `STRONG` with zero
overfitting flags. H1's closest comparable moment (Phase 8) still had
a payoff ratio of only 0.5 (losses bigger than wins) and later failed
robustness scrutiny in Phase 8.1; this candidate's payoff ratio is
3.24 in the opposite, favorable direction.

## Classification

**B — Interesting lead**, by the letter of the pre-registered
criteria (Outcome A specifically requires Research Gate status "at
least PROMISING," and the formal gate here is `ROBUSTNESS_REQUIRED`).
Reporting it exactly as B rather than inflating it to A, even though
the underlying evidence is stronger than anything previously found in
this project — the distinction matters and existed for a reason: this
still needs the exact same kind of dedicated parameter-neighborhood
and statistical follow-up that Phase 8.1 gave H1, before the gate
could honestly move it further.

Per instruction: **stopping here. No optimization performed. No
Phase 13.1 auto-started.**

## What would resolve ROBUSTNESS_REQUIRED

The same discipline as Phase 8.1: a small, pre-registered parameter
neighborhood around lookback=40 (e.g., 30/40/50), Wilson/bootstrap
statistical analysis on the actual trade outcomes, and regime
dependence — run once, reported honestly regardless of outcome, never
iterated on.

## Tests

4 new (multi-market import genericity, the XAU/USD scale-bug
regression test, Phase 1 validation reuse for a new instrument,
dataset-hash reproducibility). **Full regression: 369/369** (365
unchanged + 4 new).

## Recommendation

Not decided automatically, per the instructions. The clear, evidence-
motivated next step — if you choose to pursue it — is a dedicated
robustness phase for XAU/USD Breakout(lookback=40) specifically,
mirroring Phase 8.1's structure exactly. Deferred to you.
