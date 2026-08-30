# Phase 5 — Market Regime & Technical Feature Research

**REAL HISTORICAL RESULTS** in the "Real historical analysis" section
below — same dataset already validated in Phase 4.5. Everything else
(regime fixtures) is **SYNTHETIC TEST DATA**, clearly labeled at each use.

## Purpose

Not to make the baseline strategy profitable — it remains the
**control**, unchanged. This phase asks: does market regime or
technical context explain anything about when the baseline crossover
strategy wins or loses? The answers are descriptive observations, not
proof of causation, and not a new trading rule.

## Features implemented

| Feature | Definition | Warm-up |
|---|---|---|
| `sma_10`, `sma_50` | Same as Phase 2 (reused, not recalculated differently) | 10 / 50 candles |
| `sma_50_slope` | `(sma_50[t] - sma_50[t-5]) / 5` — 5-candle trailing rate of change | 55 candles (50 + 5) |
| `sma_distance` / `sma_distance_pct` | `sma_10 - sma_50`, and that divided by close | 50 candles |
| `rsi_14` | Wilder-smoothed RSI, standard definition | **14 candles exactly** (empirically verified — see `test_rsi_warmup_boundary_is_exactly_14_none_values`) |
| `atr_14` / `atr_percent` | Wilder-smoothed Average True Range, and ATR/close | **13 candles exactly** (empirically verified, differs from RSI's 14 because True Range has a valid fallback on the very first candle) |
| `recent_high` / `recent_low` | Rolling max(high)/min(low) over 20 candles | 20 candles |
| `rolling_range`, `distance_from_high`, `distance_from_low` | Derived from recent_high/low | 20 candles |

RSI's flat-series edge case (zero average gain AND zero average loss)
returns 50.0 (neutral) rather than NaN — a documented special case,
not a silent divide-by-zero.

## Regime definitions (exact rules — see `app/technical_engine/regime.py`)

Evaluated in this priority order:

1. **UNKNOWN** — any required input still in warm-up
2. **HIGH_VOLATILITY** — `atr_percent > 0.0015` (checked before trend — volatility takes priority)
3. **LOW_VOLATILITY** — `atr_percent < 0.0005`
4. **TRENDING_UP** — `close > sma_50` AND `sma_50_slope > 0` AND `sma_distance_pct > 0.0010`
5. **TRENDING_DOWN** — the exact mirror of TRENDING_UP
6. **RANGING** — the fallback; none of the above matched

**These thresholds were chosen once, documented, and never adjusted
against backtest results.** They are EUR/USD-1H-shaped guesses, not
calibrated — a different instrument/timeframe would likely need
different values.

## Warm-up handling

Every feature returns `None` until its own warm-up period is complete
— never a fabricated 0 or forward-filled value. Regime returns
`UNKNOWN` (not a guess) until every input it depends on is available.
Proven in `test_regime_unknown_during_warmup`.

## Lookahead protection

Same standard as Phases 1-4, proven the same way: compute features on
a dataset, append an absurd future price spike, verify every feature
value at or before the original cutoff is unchanged
(`test_future_candles_do_not_change_past_snapshots`). Also proven
individually for RSI and ATR (`test_rsi_does_not_use_future_values`,
`test_atr_does_not_use_future_values`).

## Chronological validation

Reuses Phase 2's exact `_require_chronological_order` check (imported
directly, not reimplemented) — duplicate or out-of-order candles are
rejected identically to how `technical_engine.service` already
rejects them.

## Synthetic test fixtures

`tests/fixtures/regime_fixtures.py` — **SYNTHETIC, NOT REAL MARKET
DATA** — five hand-built candle sequences (steady rise, steady fall,
sideways oscillation, high-volatility swings, insufficient data),
used only to verify the classifier produces the intended label for
each obviously-shaped input. Verified empirically before writing
assertions, same discipline as every other phase.

## Baseline trade join — timing rule

Every trade is joined to the feature snapshot at its
**`signal_timestamp`**, never `entry_timestamp`. The Phase 4 execution
model always executes one candle after the signal candle; using
entry-time features would leak one candle of hindsight into "what did
we know when we decided to trade." See
`test_context_attached_at_signal_timestamp_not_entry_timestamp`.

## Real historical analysis

Same dataset as Phase 4.5 (`ejtraderLabs/historical-data`, EUR/USD 1H,
2012-11-16 → 2022-03-04, 57,600 candles), same BASE_COST configuration,
same unmodified strategy and backtest engine — the baseline trades
here are recomputed (deterministically identical to Phase 4.5's saved
results, not a new/different baseline) and joined with the new Phase 5
feature layer. Full output: `research/results/phase_5_regime_analysis.json`.

**All 1,539 baseline trades matched to a feature snapshot** (100% —
no missing-data gaps in this join).

### Regime distribution — all 57,600 candles

| Regime | Candles | % of dataset |
|---|---|---|
| RANGING | 17,674 | 30.7% |
| HIGH_VOLATILITY | 14,730 | 25.6% |
| TRENDING_DOWN | 12,634 | 21.9% |
| TRENDING_UP | 12,146 | 21.1% |
| LOW_VOLATILITY | 362 | 0.6% |
| UNKNOWN | 54 | 0.1% |

### Baseline trades by regime (at signal time)

| Regime | Trades | Win Rate | Net P&L | Profit Factor |
|---|---|---|---|---|
| RANGING | 1,105 | 31.5% | -$1,993.10 | 0.917 |
| HIGH_VOLATILITY | 424 | 34.2% | -$2,265.30 | 0.829 |
| LOW_VOLATILITY | 10 | 20.0% | -$42.00 | 0.717 |
| **TRENDING_UP** | **0** | — | — | — |
| **TRENDING_DOWN** | **0** | — | — | — |

### The central finding of this phase

**Zero baseline trades occurred during TRENDING_UP or TRENDING_DOWN**,
despite those two regimes covering 43% of all candles in the dataset.
This is not a bug or a data gap — it's structural: a crossover signal
fires at the exact candle where SMA10 and SMA50 meet, which is by
definition the moment of *minimum* separation between them. The
TRENDING regime definition requires *sufficient* separation
(`sma_distance_pct > 0.0010`). A fresh crossover essentially can never
satisfy that at the signal candle itself — the two conditions are
close to mutually exclusive by construction.

**HYPOTHESIS (not tested, not a rule):** the SMA10/50 crossover
strategy's signal, evaluated at signal-time regime, cannot currently
be studied for "does it work better in a trend" using this exact
regime definition, because it structurally never fires inside one. A
future experiment could evaluate regime a few candles *after* entry
instead of at the signal candle, or redefine "trend" independent of
SMA separation (e.g., ADX-based), to make that comparison meaningful.

### Baseline trades by RSI zone (at signal time)

| RSI Zone | Trades | Win Rate | Net P&L | Profit Factor |
|---|---|---|---|---|
| RSI 30-50 | 704 | 31.4% | -$1,111.10 | 0.932 |
| RSI 50-70 | 686 | 31.8% | -$1,761.20 | 0.889 |
| RSI<30 | 81 | 38.3% | -$302.70 | 0.873 |
| RSI>=70 | 68 | 36.8% | -$1,125.40 | **0.601** |

**HYPOTHESIS (not tested, not a rule):** trades signaled while RSI was
already >=70 (i.e., a bullish crossover firing into an already-
overbought reading, or a bearish crossover into already-oversold —
this bucket mixes both directions) show the weakest profit factor of
the four zones. The sample size here (68 trades) is small relative to
the other buckets, so this is a hypothesis worth a dedicated
out-of-sample test, not a conclusion.

### What this data does NOT show

Every single condition bucket has a profit factor below 1.0 — there
is no regime or RSI zone in this data where the raw baseline strategy
was actually profitable. This research phase did not find a filter
that rescues the baseline; it found more detail about *how* the
baseline loses, and one structural fact (the trend/signal-timing
mismatch above) worth designing around in a future phase.

## Files created

- `app/technical_engine/regime.py`, `features.py`
- `app/technical_engine/models.py` (added `FeatureSnapshot`, existing `TechnicalFeature` untouched)
- `app/technical_engine/indicators.py` (added RSI/ATR/rolling max-min/slope, existing `calculate_sma` untouched)
- `app/research/trade_analysis.py`
- `app/api/routes/technical_analysis.py` (added `/features` endpoint, existing `/sma` untouched)
- `backend/scripts/run_phase5_regime_analysis.py`
- `tests/test_phase5_indicators.py`, `test_regime.py`, `test_features.py`, `test_trade_analysis.py`
- `tests/fixtures/regime_fixtures.py`
- `research/results/phase_5_regime_analysis.json`
- This document

## Files modified

None of Phase 1-4's strategy, backtesting, or existing model code —
only additive changes (new functions appended to `indicators.py`, new
dataclass appended to `models.py`, new route appended to
`technical_analysis.py`).

## Tests: 109/109 passing

69 from Phases 1-4.5 unchanged, 40 new (14 new-indicator tests, 7
regime-classification tests, 12 feature-service tests, 7
trade-analysis tests).

## Bugs discovered and fixed

Two, both in my own new test code (not in the engine/feature logic
itself), caught by running the suite: an incorrect expected value in
`test_slope_basic` (arithmetic slip in the test, not the slope
function) — both fixed before this report.

## Known limitations

- Regime thresholds are documented starting guesses, not calibrated —
  see the regime.py docstring's explicit warning against reusing them
  elsewhere unchanged.
- The RSI>=70 hypothesis above has a small sample (68 trades) —
  flagged as a hypothesis specifically because it isn't large enough
  to trust on its own.
- `approx_subset_max_drawdown` in the trade-analysis output is an
  approximation (cumulative P&L peak-to-trough for a filtered,
  non-contiguous trade subset) — not a real, independently-tradable
  equity curve, and documented as such in `trade_analysis.py`.

## Recommended next step

Not decided automatically, per the instructions for this phase. The
central structural finding (crossover signals never occur inside a
TRENDING regime by this definition) is a natural candidate for the
next research question — but that decision, and any hypothesis
testing that follows, is deferred to you.
