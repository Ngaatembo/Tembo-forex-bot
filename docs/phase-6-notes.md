# Phase 6 — Entry, Exit, and Strategy Research Layer

**REAL HISTORICAL RESULTS.** Same dataset as Phase 4.5/5
(`ejtraderLabs/historical-data`, EUR/USD 1H, 2012-11-16 → 2022-03-04,
57,600 candles). Six pre-registered configurations, tested across the
same chronological train/validation/out-of-sample split as Phase 4.5.

## The baseline remains the control

The unchanged Phase 3 SMA10/50 crossover strategy was never modified.
Every experiment in this phase is a variation layered on top of it —
either an entry filter (can only suppress a baseline signal, never add
one) or an exit rule (can only close a position earlier than the
baseline's opposite-crossover exit would). Proven structurally, not
just by convention: `test_baseline_exit_config_matches_phase4_baseline_engine_exactly`
confirms the new research engine reproduces Phase 4's exact trades
when no new rule is active.

## Pre-registered hypotheses

**Entry filters** (from Phase 5's descriptive findings — see
`app/strategy_engine/entry_filters.py` for full rationale):
- **E1 `entry_low_vol`** — suppress signals occurring in a
  LOW_VOLATILITY regime (Phase 5: worst win rate of any regime, 20%)
- **E2 `entry_extreme_rsi`** — suppress BUY signals with RSI≥70 or SELL
  signals with RSI≤30 (Phase 5: RSI≥70 zone had the worst profit
  factor of any RSI bucket, 0.601)

**Exit rules** (`app/backtesting/exit_rules.py`):
- **X1 `exit_fixed_stop_1pct`** — 1% fixed stop-loss, OR opposite
  crossover, whichever comes first
- **X2 `exit_atr_stop_2x`** — stop at entry ± 2×ATR14-at-entry (frozen,
  not recalculated), OR opposite crossover
- **X3 `exit_max_hold_200`** — forced exit after 200 candles (~8.3
  days) if still open, OR opposite crossover

All six configurations (baseline + 5 experiments) were fixed **before**
looking at validation or out-of-sample results — see the pre-registration
note at the top of `scripts/run_phase6_experiments.py`.

## A real bug found and fixed before any result was trusted

The first run of this experiment script produced **byte-identical
results** for `entry_low_vol`, `entry_extreme_rsi`, and `baseline` in
every single metric across all three periods. That's not a plausible
real finding — Phase 5 found ~150 RSI-extreme-zone trades out of 1,539
total, so filtering them should visibly change something. The cause:
the script called Phase 4's `run_backtest()` (which recomputes its
own fresh, unfiltered signals internally) whenever no exit rule was
active — silently discarding the filtered signal list the entry-filter
code had just computed. Fixed in `scripts/run_phase6_experiments.py`;
a regression test (`test_entry_filter_actually_changes_resulting_trades`)
now proves a filtered signal actually changes the resulting trades.
All results below are from the corrected run.

## Results — BASE_COST (spread 1 pip, slippage 0.2 pip), by period

| Configuration | Period | Trades | Return | Win Rate | Profit Factor | Max DD% |
|---|---|---|---|---|---|---|
| **baseline** | train_dev | 1,076 | -57.76% | 31.9% | 0.803 | 61.3% |
| **baseline** | validation | 200 | +17.32% | 35.0% | 1.486 | 4.8% |
| **baseline** | out_of_sample | 262 | -3.32% | 30.9% | 0.929 | 12.2% |
| entry_low_vol | train_dev | 1,066 | -57.03% | — | 0.804 | — |
| entry_low_vol | validation | 192 | +17.11% | — | 1.483 | — |
| entry_low_vol | out_of_sample | 262 | -3.32% | — | 0.929 | — |
| entry_extreme_rsi | train_dev | 864 | **-25.58%** | — | **0.890** | — |
| entry_extreme_rsi | validation | 176 | +16.47% | — | 1.548 | — |
| entry_extreme_rsi | out_of_sample | 232 | **-4.21%** | — | **0.901** | — |
| exit_fixed_stop_1pct | train_dev | 1,076 | -53.13% | — | 0.815 | 57.2% |
| exit_fixed_stop_1pct | validation | 200 | +17.60% | — | 1.498 | 4.8% |
| exit_fixed_stop_1pct | out_of_sample | 262 | -3.37% | — | 0.928 | 12.2% |
| exit_atr_stop_2x | train_dev | 1,076 | **-33.32%** | 26.1% | 0.852 | **38.0%** |
| exit_atr_stop_2x | validation | 200 | +13.31% | — | 1.423 | 5.1% |
| exit_atr_stop_2x | out_of_sample | 262 | -4.87% | — | 0.881 | 11.2% |
| exit_max_hold_200 | *all periods* | *identical to baseline* | | | | |

(Full per-experiment JSON: `research/results/phase_6_summary.json`;
append-only experiment registry with every run's full context:
`research/results/phase_6_experiments.json`.)

Zero-cost diagnostic (full period, baseline, never the headline
number): 1,539 trades, -21.46% return — retained only as a reference
point, exactly as Phase 4/4.5 established.

## Per-hypothesis verdict

**entry_low_vol — REJECTED (negligible effect).** Only ~10-15 trades
removed per period (LOW_VOLATILITY is a rare regime, 0.6% of candles
per Phase 5). Barely moves any metric. Not wrong, just too rare to
matter.

**entry_extreme_rsi — REJECTED (does not generalize).** This is the
clearest out-of-sample discipline lesson in this phase. On train_dev —
the period the hypothesis was inspired from — it looks like a real
improvement: return goes from -57.8% to -25.6%, profit factor from
0.803 to 0.890. But on out-of-sample data it's **worse than baseline**,
not better (-4.21% vs -3.32% return, 0.901 vs 0.929 profit factor). A
pattern that holds on the period that generated the hypothesis but
reverses on unseen data is close to the textbook definition of
overfitting to that period, even with a economically-motivated,
pre-registered rule. This is exactly the failure mode the out-of-sample
discipline in this phase exists to catch.

**exit_fixed_stop_1pct — REJECTED (too small an effect to matter).**
Modest, inconsistent movement in every metric, in both directions
depending on period. Trade count is completely unchanged (1,076/200/262,
identical to baseline) — the 1% stop essentially never triggers before
the opposite crossover would have exited anyway.

**exit_atr_stop_2x — PARTIALLY PROMISING, but not for return.** Return
improves substantially on train_dev (-57.8% → -33.3%) but *worsens* on
both validation and out-of-sample — same overfitting pattern as
entry_extreme_rsi, and rejected as a profitability claim on the same
grounds. **However:** maximum drawdown drops sharply and consistently
in the period where the strategy loses most — 61.3% → 38.0% on
train_dev, with smaller but present drawdown reduction elsewhere. This
is a genuinely interesting, separate hypothesis worth its own
follow-up: **ATR-based stops may be a risk-control tool even when they
aren't a return-improvement tool** — those are different claims, and
this data supports the first, not the second.

**exit_max_hold_200 — INCONCLUSIVE (rule never actually bound).** Zero
effect on every metric, in every period, because in the real dataset
**only 1.1% of trades ever hold past 200 candles** (mean holding time:
52.9 hours; median: 36.0 hours). This isn't evidence the hypothesis is
wrong — it's evidence 200 candles was too loose a threshold to test it
at all. A future experiment testing this hypothesis meaningfully would
need a much shorter threshold, informed by the actual holding-time
distribution above.

## Trade distribution (baseline, full period, 1,539 trades)

- Mean holding time: 52.9 hours | Median: 36.0 hours | Max: 399 hours
- **Profits are not concentrated in a few large trades**: the top 3
  winning trades account for only 4.0% of total gross profit. This
  matters — a strategy propped up by a handful of outlier trades would
  be a fragile, low-confidence result; broad-based, consistent losses
  across 1,539 trades (as seen here) is a stronger, more trustworthy
  signal that there genuinely is no edge, not just bad luck on a few
  trades.
- Largest single win: $579.90 | Largest single loss: -$280.60 — no
  outlier trade dominates either direction.

## Out-of-sample discipline — how it was actually followed

1. All six hypotheses (2 entry, 3 exit) were fixed and coded before
   the script was ever run.
2. The script always evaluates train_dev, validation, and
   out_of_sample together in one run — there was no repeated tuning
   loop against validation or out-of-sample data.
3. When entry_extreme_rsi and exit_atr_stop_2x looked promising on
   train_dev, they were **not** modified, re-parameterized, or re-run
   with adjusted thresholds after seeing that. Their out-of-sample
   results are reported exactly as the first and only run produced
   them.

## Lookahead protection

Same standard as every prior phase, proven the same way at the new
engine's own level: `test_future_candles_do_not_change_earlier_stop_trigger`
appends an absurd future candle and confirms the earlier stop-loss
trigger is unaffected. Combined with the already-proven lookahead
safety of the indicator/strategy layers this engine sits on top of.

## Tests: 155/155 passing

109 from Phases 1-5 unchanged, 46 new (entry filters, exit rule config
and price derivation, risk sizing model with fail-closed checks, the
research engine's stop/target/max-holding mechanics with hand-verified
exact trigger prices, the baseline-equivalence regression check, the
lookahead check, and the experiment-framework's append-only
reproducibility guarantees).

## Files created

- `app/strategy_engine/entry_filters.py`
- `app/backtesting/exit_rules.py`, `risk_config.py`, `engine_research.py`
- `app/research/experiment.py`
- `tests/test_entry_filters.py`, `test_exit_rules.py`, `test_risk_config.py`, `test_engine_research.py`, `test_experiment_framework.py`
- `backend/scripts/run_phase6_experiments.py`
- `research/results/phase_6_summary.json`, `phase_6_experiments.json`
- This document

## Files modified

- `app/backtesting/portfolio.py` — additive only: new optional fields
  (default `None`) on the internal position record, and two new
  methods (`check_exit_conditions`, `close_position_at_price`) used
  only by the new research engine. Every Phase 4 baseline call site is
  unaffected — proven by the baseline-equivalence regression test.
- `tests/test_backtest_security_boundary.py` — extended to also scan
  `app/research/` for any broker-adapter reference (still zero).

## Known limitations

- Stop/take-profit fills in the research engine execute at the exact
  trigger price with no additional spread/slippage — a real stop order
  can slip past its trigger in fast markets; documented in
  `portfolio.close_position_at_price`.
- When both a stop and a target fall within the same candle's
  high-low range, the engine checks the stop first (conservative
  assumption — real intra-candle order is unknowable from OHLC data
  alone).
- ATR-based exits use ATR frozen at entry, not a trailing/recalculated
  ATR — a genuinely different (more complex) hypothesis, not built here.
- Risk-based (percent-of-equity) position sizing is implemented and
  tested in isolation but deliberately not used in any comparison
  experiment this phase, to keep position size constant and isolate
  the entry/exit rule as the only variable under test.

## Recommended next research phase

Not decided automatically, per the instructions for this phase. Two
concrete candidates fall directly out of this phase's honest results:
(1) a dedicated, narrower test of ATR-stop drawdown reduction as a
risk-control hypothesis (separate from a return-improvement claim),
and (2) redesigning the max-holding-period experiment with a threshold
actually informed by the real 36-hour median holding time. Neither
decision is made here — deferred to you.
