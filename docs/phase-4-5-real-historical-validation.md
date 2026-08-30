# Phase 4.5 — Real Historical EUR/USD Validation

**REAL HISTORICAL RESULTS — not synthetic.** Everything in this
document comes from genuine market data. Where earlier phases used
synthetic fixtures for testing, that is explicitly noted; nothing
below is synthetic.

## Data source

- **Provider:** [ejtraderLabs/historical-data](https://github.com/ejtraderLabs/historical-data)
  (public GitHub repository, Apache-2.0 license)
- **File:** `EURUSD/EURUSDh1.csv`, fetched from `raw.githubusercontent.com`
- **Format:** `Date,open,high,low,close,tick_volume`, prices scaled
  ×100,000 (MT4/MetaTrader export convention — 127801 means 1.27801)
- **SHA256 of the exact file used:** recorded in
  `research/results/phase_4_5_summary.json` under `metadata.csv_file_sha256`
- **Period:** 2012-11-16 to 2022-03-04 (~9.3 years)
- **Candle count:** 57,600 hourly candles
- **Timezone — known limitation:** the source does not document what
  timezone its timestamps are in. MT4-style exports are commonly in
  broker server time (often UTC+2/+3), not UTC. We treated timestamps
  as-is, labeled UTC, without a shift — see
  `app/data_engine/importers/ejtrader_source.py` for the full
  discussion. A few-hour constant offset would shift exact trade
  entry/exit hours but not the overall shape of the result (trade
  count, sign of the edge, drawdown magnitude).

Prices were sanity-checked against known EUR/USD history: 1.278 in
November 2012 and 1.093 in March 2022 both match real historical
exchange rates for those dates.

## Data quality audit

Ran through Phase 1's unmodified `validate_candles()`:

```
Total candles:        57,600
OHLC violations:      0
Zero/negative prices: 0
Duplicate timestamps: 0
Unexpected gaps:      14 (weekend closures already excluded automatically)
Overall clean:        True
```

The 14 flagged gaps are all genuine holiday closures (Christmas, New
Year) and daylight-saving-time transition weekends pushing slightly
past the normal ~48h weekend allowance — not data corruption. Nothing
was auto-repaired; these are reported for the record, as the spec
requires.

## Strategy (unchanged from Phase 3)

EUR/USD, 1H, SMA10/SMA50 crossover, signal only on the crossing
candle, execution at next candle's open, one position at a time. **No
parameters were changed. No alternative periods were tested.**

## Configuration

A real limitation surfaced immediately: Phase 4's example default
(`$1,000` balance, `10,000`-unit position size) is a ~10:1+ notional
ratio with no margin-call modeling, and produced a nonsensical deeply
negative account balance. Per the Phase 4 spec's own instruction
("do not make position size unrealistically large"), this run instead
uses:

```
initial_balance: $10,000
position_size:   10,000 units (1:1 notional — no effective leverage)
execution_model: next_open (unchanged)
end_of_data_policy: close (unchanged)
```

This is flagged explicitly as a real gap surfaced by real data: the
backtester still has no margin-call/stop-out simulation, so any
position size large enough relative to account size can still produce
an uninterpretable result. That remains a known limitation either way
(see below).

## Transaction cost sensitivity — full period, all 57,600 candles

| Tier | Spread | Slippage | Trades | Return | Profit Factor | Max Drawdown |
|---|---|---|---|---|---|---|
| ZERO_COST_DIAGNOSTIC | 0 | 0 | 1,539 | **-21.46%** | 0.941 | 50.8% |
| LOW_COST | 0.5 pip | 0.1 pip | 1,539 | -32.23% | 0.912 | 56.1% |
| BASE_COST | 1 pip | 0.2 pip | 1,539 | -43.00% | 0.885 | 61.3% |
| HIGH_COST | 2 pip | 0.5 pip | 1,539 | -67.63% | 0.827 | 77.8% |

**The most important number in this table is the zero-cost row.** Even
with *zero* trading friction assumed, the strategy loses money
(profit factor 0.94, well below the 1.0 break-even line) — meaning
**the raw SMA10/50 crossover signal itself has no edge on this data,
before any real-world cost is even applied.** Every additional cost
tier makes an already-losing strategy worse, which is exactly what
you'd expect from a strategy with no underlying edge and a large
number of trades each paying the spread.

## Chronological period split (BASE_COST, unchanged strategy in every period)

| Period | Dates | Candles | Trades | Return | Profit Factor |
|---|---|---|---|---|---|
| TRAIN_DEV (70%) | 2012-11-16 → 2019-05-24 | 40,320 | 1,076 | **-57.76%** | 0.803 |
| VALIDATION (15%) | 2019-05-24 → 2020-10-14 | 8,640 | 200 | **+17.32%** | 1.486 |
| OUT_OF_SAMPLE (15%) | 2020-10-14 → 2022-03-04 | 8,640 | 262 | -3.32% | 0.929 |

No parameter changed between these three runs — same strategy, same
cost assumptions, different slices of the same real dataset.

## Drawdown analysis (BASE_COST, full period)

- **Maximum drawdown:** 61.3% ($6,542.80 on the $10,000 account)
- **Equity peaked** at $10,669.60 on **2012-12-19** — barely a month
  into the dataset
- **Drawdown trough:** $4,126.80 on **2017-09-25**
- **The account never recovered back to its initial peak for the
  remainder of the ~9.3-year dataset.**
- Maximum consecutive losing trades: 20

A strategy that spends effectively its entire tested history under
water, never fully recovering, is not a marginal or borderline case —
this is an unambiguous result.

## Interpretation

The unchanged Tembo SMA10/50 crossover strategy, tested on 9.3 years
of real EUR/USD 1H data:

- **Loses money even before any trading cost is applied** (zero-cost
  profit factor 0.94). This is the central finding — it means the
  crossover signal itself carries no discernible edge on this
  instrument/timeframe, independent of execution cost.
- **Loses more as realistic costs are added**, consistent with a
  large-trade-count, no-edge strategy bleeding out through the spread.
- **Performance is not consistent across time.** The strategy lost
  heavily in the first 70% of the data, was profitable in the
  validation slice (which happens to include the 2020 COVID
  volatility spike — a single unusual regime, not sustained edge),
  and was roughly flat-to-negative in the final out-of-sample slice.
  This inconsistency — profit concentrated in one unusual 15% slice
  out of three — is itself evidence against a real, repeatable edge,
  not evidence for one.
- **1,539 trades is a large enough sample** that this is not a
  small-sample-size fluke — the zero-cost sub-1.0 profit factor across
  a nine-year, 1,500+ trade sample is a meaningful negative result, not
  statistical noise.
- **Maximum drawdown of 61.3%, with no recovery by the end of the
  dataset**, would be operationally unacceptable for real trading
  regardless of the return figure.

**This result does not prove the strategy will lose money in the
future** — markets change, and this is one dataset, one instrument,
one timeframe, one (unoptimized) parameter pair. But it does establish
an honest, unfavorable baseline: **the simplest possible version of
this strategy shows no edge on this real data**, which is itself
valuable, actionable information for deciding what (if anything) to
build next.

## Whether the result is promising, weak, or inconclusive

**Weak — not inconclusive.** The sample size is large enough (1,539
trades, 9.3 years, tested across three separate sub-periods) that this
is a real, meaningful negative result rather than "not enough data to
tell." The strategy does not merely fail to overcome costs; it loses
even at zero cost.

## Files created

- `app/data_engine/importers/csv_importer.py` — generic CSV import interface
- `app/data_engine/importers/ejtrader_source.py` — source-specific adapter
- `app/data_engine/quality_audit.py` — data quality audit/report module
- `backend/scripts/run_real_historical_validation.py` — reproducible CLI
- `tests/test_csv_importer.py` — 9 new tests
- `tests/fixtures/sample_data/sample_ejtrader_eurusd_h1.csv` — small real-data excerpt for tests
- `research/results/README.md`, `phase_4_5_summary.json`, `phase_4_5_base_cost_trades.json`
- This document

## Files modified

None — Phase 4's backtesting engine and Phase 3's strategy were used exactly as-is.

## Existing/new/total tests

69/69 passing — 60 from Phases 1-4 unchanged, 9 new (real-format
parsing, invalid-row rejection, missing-column rejection, duplicate
detection via the reused Phase 1 validator, out-of-order sorting via
the reused Phase 1 normalizer, clean validation on real data,
determinism, full-pipeline wiring, and a lookahead-bias check on
real-data-shaped input).

## Bugs discovered and fixed

None in Phase 1-4 code. One **configuration** issue was caught and
corrected before producing headline numbers: the Phase 4 example
default position size (10,000 units against a $1,000 account) is
unrealistically large per the Phase 4 spec's own explicit instruction,
and produces a nonsensical deeply-negative balance with no margin-call
modeling. This run uses a 1:1 notional ratio instead, documented above.

## Known limitations

- No margin-call/stop-out simulation — a sufficiently large position
  size relative to account size can still produce an uninterpretable
  negative-balance result. This should be added before any position
  size much larger than 1:1 is used.
- Timezone of the source timestamps is unconfirmed (see Data Source
  section above).
- Only one instrument, one timeframe, one unoptimized parameter pair
  was tested — this says nothing about SMA crossovers in general,
  only about this exact configuration.
- No out-of-sample data exists beyond March 2022 in this dataset —
  the "out-of-sample" period here is still historical, not a live
  forward test.

## Recommended next step

Not decided automatically. Given this baseline, options include:
reviewing whether a fundamentally different strategy family is worth
building (the spec's own framing: "if the baseline strategy is weak,
that becomes valuable information for designing future filters"), or
adding margin/stop-out modeling to the backtester before testing
anything with real leverage. Decision deferred to you, per the
instructions for this phase.
