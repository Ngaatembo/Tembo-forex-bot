# Phase 13.1 — XAU/USD Breakout Robustness (Classification: A, with an explicit statistical caveat)

**REAL RESULTS.** Same XAU/USD 1H dataset and methodology as Phase 13,
same corrected notional position sizing (`8.298`, derived from
EUR/USD-comparable exposure).

## Provenance note

The robustness script and its tests already existed, untracked, before
I took any visible action this turn — same phenomenon as Phase 7/9.1.
Per established practice: I read both files in full myself, ran the
tests myself (2/2 pass), ran a manual security scan myself (clean),
and then **ran the actual experiment myself** rather than trusting
printed output — it reproduced Phase 13's exact lookback=40 numbers
byte-for-byte. Verified, not assumed.

## Robustness result — the headline finding

**All three lookbacks (30, 40, 50) independently reach `Verdict:
PROMISING`.** 40 sits stably in the middle of the neighborhood, not a
lone peak — the opposite of H1's fragile Phase 8.1 finding (where the
chosen value sat at an isolated spike surrounded by worse neighbors).

| Lookback | Dev PF | Val PF | OOS PF | OOS Trades | Max DD% | HIGH-cost OOS PF |
|---|---|---|---|---|---|---|
| 30 | 1.073 | 1.714 | 1.066 | 176 | 20.2% | 1.066 (unchanged) |
| **40** | **1.072** | **1.572** | **1.061** | **158** | **18.5%** | **1.061 (unchanged)** |
| 50 | 1.067 | 1.559 | 1.024 | 133 | 17.0% | 1.024 (unchanged) |

Full LOW/BASE/HIGH detail, scorecard, and gate output for all three in
`research/results/phase_13_1_xauusd_robustness.json`.

## Full Scorecard + Gate (all three lookbacks)

| Lookback | Edge | Robustness | Risk | Statistical | Realism | Gate |
|---|---|---|---|---|---|---|
| 30 | STRONG | STRONG | STRONG | WEAK | STRONG | PROMISING |
| 40 | STRONG | STRONG | STRONG | WEAK | STRONG | PROMISING |
| 50 | STRONG | STRONG | STRONG | WEAK | STRONG | PROMISING |

**`PROMISING` gate status has never been reached by any candidate in
this project before this phase** — not H1, not any Phase 9-13
configuration. Zero overfitting flags across all three.

## Statistical analysis — the one weak link, stated plainly

For lookback=40: win rate 24.7%, payoff ratio 3.24, breakeven win rate
23.6% — the actual win rate clears breakeven, consistent with the
positive profit factor. But:

- **Wilson 95% CI on win rate: (18.6%, 32.0%)** — this interval
  **contains** the 23.6% breakeven rate. We cannot rule out, at 95%
  confidence, that the true win rate is exactly at breakeven.
- **Bootstrap 95% CI on total OOS P&L: (-$3,459, +$4,966)** — this
  interval **contains zero.**

**This is the honest, load-bearing caveat on this entire result:**
despite a remarkably stable pattern across three independently-tested
lookbacks, zero overfitting flags, and cost-insensitivity, the sample
size (133-176 OOS trades per lookback) is not yet large enough to
statistically exclude "no real edge" at 95% confidence. This is
exactly why the Research Gate — designed with this precise distinction
in mind — stops at `PROMISING` rather than advancing to
`PAPER_CANDIDATE`, which explicitly requires `STATISTICAL: STRONG`.

## Regime analysis — a significant, specific finding

For lookback=40, **100% of the 158 out-of-sample trades occurred
during `HIGH_VOLATILITY` regime candles — zero trades in any other
regime for this specific OOS window.** This is not merely "concentrated
in one regime among several" — it's the entire evidence base for this
lookback's OOS period coming from a single regime classification. This
does not on its own invalidate the finding (the strategy's mechanism —
breaking a prior price range — is plausibly a genuinely
volatility-driven phenomenon), but it means: **this evidence says
nothing yet about how the strategy behaves in RANGING or
TRENDING-only conditions**, and if HIGH_VOLATILITY conditions become
rarer in the future, trade frequency could drop sharply. Reported as a
finding, not filtered into a new strategy variant.

## Generalization audit — instrument-specific vs. timeframe-specific assumptions

**Instrument-specific, and already correctly isolated:**
- Breakout's core mechanism (prior-range comparison) is scale-relative
  by construction — no absolute price thresholds, transfers cleanly.
- ATR-stop multiple (2.0x) is dimensionless — transfers cleanly.
- **Position sizing is the real gap.** Phase 13 required a manually
  hand-computed, per-script notional correction (`8.298` for XAU/USD)
  because `BacktestConfig`'s fixed unit-count `position_size` has no
  built-in notion of comparable notional exposure across instruments.
  This is genuine missing core infrastructure, not a one-off script fix.
- CSV price-scale (5-decimal forex vs. 2-decimal gold) is already
  correctly isolated to the import layer (`ejtrader_import_config` vs.
  `ejtrader_xauusd_import_config`) — this is the right pattern, just
  not yet generalized into a clean per-instrument registry.

**Timeframe-specific, not yet addressed:**
- `max_holding_candles=100` and the 30/40/50 lookback values are all
  **candle counts** — their real-world time duration changes entirely
  with timeframe (100 candles ~4 days on 1H, but ~1 day on 15M or
  ~16 days on 4H). None of these values are portable to a different
  timeframe without the same "check the real trade-duration
  distribution first" discipline used in Phase 9/11 — never assumed.
- Regime classification thresholds (Phase 5's HIGH_VOLATILITY/
  LOW_VOLATILITY ATR% cutoffs) were calibrated to EUR/USD 1H's own
  distribution — untested on XAU/USD or other timeframes, though
  reused unmodified here per instruction.

## Architecture audit for the eventual general trading engine

**Already exists and is reusable as-is:** the full research pipeline
(hypothesis -> experiment -> verdict -> scorecard -> gate -> priority ->
candidate), a working multi-instrument import pattern (proven across
3 instruments now), the backtesting engine with pluggable exit rules,
regime classification, and a structurally-locked execution boundary
(`app.execution`/`app.risk_engine` genuinely unreachable from research
code, verified by dedicated tests in every phase since Phase 7).

**Missing, and required before any live/paper work:**
1. **Notional-aware position sizing built into the core engine**, not
   hand-computed per script — the gap this phase's manual correction
   exposed directly.
2. **A real Instrument/Timeframe Adapter** — today, every phase's
   script hand-wires its own CSV path and import config. A clean
   `(instrument, timeframe) -> Candle stream` interface would replace
   this ad-hoc pattern, now that the same pattern has been proven
   correct across EUR/USD, GBP/USD, and XAU/USD.
3. **A live Strategy Selector** — Phase 10's `/research/candidates`
   API is read-only historical reporting; nothing today can answer
   "given instrument X and timeframe Y right now, does a validated
   (`PROMISING`+) candidate apply?" as a live query.
4. **Risk infrastructure beyond `RiskConfig`'s unused percent-sizing**
   — no daily loss limits, max concurrent positions, or emergency
   shutdown exist anywhere yet, even at the design level.
5. **Explainability formatting** (Step 8's example decision output) —
   likely a thin, pure-function report generator over data that
   mostly already exists; not built this phase, but genuinely small.

**Correctly NOT built, and should stay that way for now:** any
MT5/broker adapter, any paper-trading infrastructure. Neither is
justified yet — the strongest candidate this project has produced
still has a `WEAK` statistical category, and Phase 10's own gate design
already refuses to call anything `PAPER_CANDIDATE` until that clears.
Building execution infrastructure ahead of that evidence would
contradict the project's own standing discipline.

## Classification: A, with the caveat stated as loudly as the result

**A — Robust candidate**, by the letter of the pre-registered criteria:
positive OOS PF, reasonable trade count (133-176), consistent
development->validation->OOS (all three lookbacks, all >1.0
everywhere), positive at BASE cost, positive at HIGH cost,
acceptable drawdown (17-20%), no overfitting flags, Research Gate
reaches `PROMISING` — first time in this project.

**The one criterion not fully met: "statistical evidence supportive
of an edge."** The evidence is *consistent with* an edge (stable
across lookbacks, positive everywhere, cost-insensitive) but does not
yet *statistically exclude chance* at 95% confidence. This is reported
as the load-bearing limitation of an Outcome-A classification, not
buried in a footnote. **Per instruction: no optimization performed,
no Strategy #6 created, no live/paper trading started.**

## Tests

2 new (lookback-neighborhood mechanism proof — including an honestly
documented dead-end where an earlier synthetic scenario using a
monotonic price series proved mathematically incapable of
distinguishing lookbacks, not a bug — and XAU/USD import
reproducibility). **Full regression: 371/371** (369 unchanged + 2 new).

## Recommendation

Not decided automatically, per instruction. The evidence justifies
bringing this back for a decision on the next phase — most likely
either (a) a dedicated effort to grow the statistical sample (more
history if a legitimate source can be found, or accepting the current
evidence as the practical ceiling given known data limits), or (b) a
decision on whether `PROMISING`-but-not-`PAPER_CANDIDATE` evidence is
itself sufficient to justify beginning the general-engine
infrastructure work (Adapter, notional sizing, Strategy Selector)
identified above, independent of any specific strategy's final status.
Both are your call, not mine.
