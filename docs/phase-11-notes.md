# Phase 11 — Time-Series Momentum / Trend-Following (REJECTED)

**REAL RESULTS.** Same EUR/USD 1H dataset, same 70/15/15 split, same
three cost tiers used since Phase 4.5.

## What was tested

Six pre-registered hypotheses, frozen before any result was seen:

- **T1** (pure momentum sign, `close[t]/close[t-N]-1`): lookbacks 20/60/120/240
- **T2** (volatility-normalized): lookback 60, threshold 6.0× ATR% —
  calibrated from this dataset's own momentum/ATR% ratio distribution
  (median ≈3.8, so 1.0-2.0 barely filters anything; 6.0 ≈ 75th
  percentile, a genuinely selective cutoff) — chosen before any backtest ran.
- **T3** (dual-lookback confirmation): primary 60, secondary 15 (60/4)

Exit: Phase 6's `ExitConfig` reused unmodified — ATR stop (2.0×,
same value as Phase 6/9) + max holding (120 candles, the actual
90th-percentile trade duration of T1 lookback=60's own trades —
calibrated from data, not guessed).

**Caveat stated up front, per the research spec:** these lookbacks
(0.8–10 days on 1H data) are short/medium-term trend-following, not a
literal replication of academic monthly-scale TSMOM — a longer lookback
would leave too few independent trend events in the ~12,000-candle OOS
window to trust.

## Results (BASE cost)

| Hypothesis | Dev PF | Val PF | OOS PF | Verdict | Gate |
|---|---|---|---|---|---|
| T1 lookback=20 | 0.843 | 0.897 | 0.723 | REJECTED | REJECT_EARLY |
| T1 lookback=60 | 0.802 | 1.216 | 0.754 | REJECTED | REJECT_EARLY |
| T1 lookback=120 | 0.869 | 0.894 | 0.874 | REJECTED | REJECT_EARLY |
| T1 lookback=240 | 0.918 | 0.928 | 0.672 | REJECTED | REJECT_EARLY |
| T2 vol-normalized | 0.849 | 1.187 | 1.173 | REJECTED | REJECT_EARLY |
| T3 confirmed | 0.818 | 1.433 | 0.800 | REJECTED | REJECT_EARLY |

**All six REJECTED at development itself** — clean, unambiguous, no
boundary cases like H1's exact-1.000 result. Full LOW/BASE/HIGH detail
in `research/results/phase_11_momentum_results.json`.

## The one real pattern worth reporting

Payoff ratio is consistently favorable across all six (1.9×–3.5× —
wins meaningfully bigger than losses, the genuine shape a real
trend-following mechanism should have). But out-of-sample win rates
(21–27%) sit clearly **below** the breakeven rate that payoff ratio
requires (~28–38%, depending on hypothesis). **The directional
mechanism has the right shape but not enough hit rate to clear its
own breakeven bar.** T2 is the most cost-robust of the six
(`REALISM=STRONG`, survives even HIGH cost) but still gate-rejected —
development itself never worked.

## Verification performed before trusting results

- 11 signal-generator tests + 3 engine-integration tests, all passing
  (lookahead, warm-up, edge-triggered firing, execution timing,
  last-candle handling)
- One real test-authoring mistake caught and fixed during writing:
  two engine tests assumed a single clean signal but the chosen price
  scenario produced an incidental leading SELL from the first valid
  (negative) momentum transition — correct code behavior, wrong test
  assumption; fixed by choosing scenarios where the first valid
  transition matches the intended test direction.
- Full regression: 361/361 (346 unchanged + 15 new)
- Security: dedicated test + manual scan — no execution/broker imports
- Reproducibility: `run_phase11_momentum.py` is deterministic, same
  inputs every run

## Verdict

**All six candidates: `REJECTED` → gate `REJECT_EARLY`.** No
candidate reaches even `RESEARCH` status, let alone `PROMISING`.
Per the pre-registered instruction: **no T4/T5/T6, no further
momentum tuning.** This family is closed on current evidence.

## Recommendation

A strategic decision, not a technical one: mean_reversion and
volatility families remain `ACTIVE` (not saturated) in Phase 10's
tracking; momentum now joins breakout as clearly rejected. The
project has tested four structurally distinct mechanisms (crossover,
mean-reversion, breakout, momentum) with none producing evidence
past `REJECT_EARLY`/`CLOSED`. Deferred to you.
