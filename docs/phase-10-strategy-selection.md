# Phase 10 — Strategy Selection & Research Efficiency Engine

## Why this phase exists

By Phase 9.1, Tembo had tested the SMA10/50 baseline, five filter/exit
variations on it, two structurally different hypotheses (H1, H2), and
three breakout lookbacks with regime filtering — 12+ individual
experiments, most rejected, one (H1) landing exactly on a pass/fail
boundary. Without a system to organize that history, the natural next
step would have been "try another strategy" — which risks becoming an
unstructured loop: generate an idea, test it, reject it, generate
another, forever, without ever asking *where* research effort is
actually justified or *why* a family keeps failing. Phase 10 builds
the infrastructure to ask those questions with evidence instead of
instinct.

## `StrategyCandidate` — why it exists

A `StrategyCandidate` (`app/research/strategy_candidate.py`) is not a
new experiment and not executable strategy code — it's a label that
says "these `ResearchExperiment` records, taken together, are one
research investigation." Before Phase 10, H1's Phase 8 experiment and
its Phase 8.1 robustness follow-up were two disconnected JSON records
with nothing linking them as one line of inquiry. A `StrategyCandidate`
holds only `experiment_ids` (plain string references, never copies of
the underlying data), is immutable once built, and can hold no
callable, code, or executable content of any kind — matching the
project's standing rule that research history is never overwritten.

## How follow-ups are grouped without double-counting

`family_saturation.py` deliberately does no deduplication logic
itself — it counts whatever `CandidateEvidenceSummary` records it's
given, one per *logical* candidate. Correct grouping is the
responsibility of whoever builds that list. In practice
(`scripts/reconstruct_phase10_candidates.py`): H1 is **one** candidate
referencing both its Phase 8 experiment and its Phase 8.1 follow-up
(`experiment_count=2`); each breakout lookback is **one** candidate
referencing its Phase 9 result plus all 3 of its Phase 9.1 regime-filter
variants (`experiment_count=4`). A dedicated test
(`test_no_double_counting_when_records_correctly_grouped`) proves the
aggregator itself would happily double-count if fed incorrectly split
records — the correctness lives in the reconstruction step, not magic
inference.

## Scorecard — five categories, never a single number

`scorecard.py` never produces a numeric score or a weighted sum.
Every category is one of `STRONG` / `MODERATE` / `WEAK` / `UNKNOWN`,
with a short, traceable reason:

- **EDGE** — inherits the existing `Verdict` directly (never
  re-derives profitability); a great development result can never
  produce a strong EDGE if out-of-sample failed, because `Verdict`
  already encodes that.
- **ROBUSTNESS** — checks the (optional) parameter neighborhood: all
  neighbors above 1.0 profit factor -> `STRONG`; a lone peak at the
  chosen value -> `WEAK` (H1's real finding); no neighborhood tested
  -> `UNKNOWN`, never assumed positive.
- **RISK** — drawdown and payoff ratio, derived directly from existing
  `BacktestSummary` fields; a high win rate with a poor payoff ratio
  (H1's real shape) cannot reach `STRONG`.
- **STATISTICAL** — Wilson and bootstrap confidence intervals, when
  available; `UNKNOWN` when they haven't been run (true for every
  candidate except H1, which got a dedicated Phase 8.1 follow-up).
- **REALISM** — whether the result survives BASE and HIGH transaction
  costs, not just a single cost assumption.

## Research Gate — sits above Verdict, never replaces it

Six states: `REJECT_EARLY`, `RESEARCH`, `ROBUSTNESS_REQUIRED`,
`PROMISING`, `PAPER_CANDIDATE`, `CLOSED`. `REJECT_EARLY` (verdict
`REJECTED` — failed at the cheapest check) and `CLOSED` (verdict
`OUT_OF_SAMPLE_FAILED` — the full three-period pipeline ran and still
failed) are deliberately different labels for two different negative
outcomes, reflecting how much evidence was gathered before the
negative conclusion. `PAPER_CANDIDATE` requires `STRONG` robustness
**and** `STRONG` statistical evidence, `MODERATE`+ risk and realism,
and zero overfitting flags — a genuinely high bar. **Its own reason
text explicitly states it does not authorize trading**, and nothing
in this module has any execution capability regardless of status.

## Family Saturation

A `HypothesisType` family (reused directly from Phase 7 — no second
taxonomy) is `SATURATED` when it has at least 3 distinct candidates
**and** 80%+ of them are negative — both documented, not tuned
against any actual family's results. A single genuine positive lead
never gets buried by a majority of unrelated failures in the same
family.

## Research Priority

`HIGH` / `MEDIUM` / `LOW` / `CLOSED` — research value, never
profitability. The one subtlety: `ROBUSTNESS_REQUIRED` covers both "a
positive result blocked only by missing evidence" and "a genuinely
weak, inconsistent result," so priority also checks the EDGE score to
tell them apart. This directly implements the project's own example:
a promising-but-unproven candidate outranks a fully rejected family,
even though both are technically "unresolved."

## The five reconstructed real candidates

Built from actual Phase 8/8.1/9/9.1 data — no new backtests:

| Candidate | Family | Verdict | Gate | Priority |
|---|---|---|---|---|
| H1 - Range-Extreme Mean Reversion | mean_reversion | OUT_OF_SAMPLE_FAILED | CLOSED | CLOSED |
| H2 - Volatility Squeeze Breakout | volatility | REJECTED | REJECT_EARLY | CLOSED |
| Breakout (lookback=20) | breakout | REJECTED | REJECT_EARLY | CLOSED |
| Breakout (lookback=40) | breakout | REJECTED | REJECT_EARLY | CLOSED |
| Breakout (lookback=60) | breakout | REJECTED | REJECT_EARLY | CLOSED |

**What this shows:** every candidate tested so far is closed. The
`breakout` family (3 candidates, 100% negative) is correctly flagged
`SATURATED` — the system independently arrives at the same conclusion
already reached by hand in Phase 9.1's own report: further breakout
lookback variations have low research value without a structurally
different idea. `mean_reversion` and `volatility` remain `ACTIVE`
(only one candidate tested each) — not saturated, just closed on the
evidence gathered so far, with room for a genuinely different
mean-reversion or volatility idea to be judged on its own merits.

## How this prevents endless random strategy testing

Before Phase 10, nothing stopped "test another breakout variant" as
the default next move even after three lookbacks and twelve
filter combinations had already failed. Now: querying
`/research/families` before proposing new work shows `breakout` is
`SATURATED` — a concrete, evidence-based signal to look elsewhere
rather than a fourth lookback value. This is a deterrent built from
history, not a hard block — nothing prevents testing a fourth
breakout variant if there's a genuinely new reason to; it just makes
the cost of doing so visible instead of invisible.

## Research vs. paper trading vs. MT5 demo vs. live execution

Four genuinely different stages, and Phase 10 only ever touches the first:

- **Research** (everything built through Phase 10): historical
  backtesting, evidence scoring, gate classification. No market
  connection of any kind, real-time or otherwise.
- **Paper trading** (not built): a live or near-live data feed with
  simulated order execution — money never at risk, but *time* is real
  and results can't be replayed identically. A `PAPER_CANDIDATE` gate
  status means a human *may* consider this step, not that it happens.
- **MT5 demo** (not built): a real broker connection with a demo
  account — real execution infrastructure and real API surface, but
  fake money. This is where actual order-placement code would first
  exist in this project.
- **Live execution** (not built, structurally locked since Phase 0):
  real money. Requires `ENABLE_LIVE_EXECUTION=true` **and** a real
  broker adapter implementation that doesn't exist — a deliberate
  two-part gate, not a single flag.

## Explicit statement: nothing in Phase 10 authorizes live trading

No file created in this phase imports `app.execution` or
`app.risk_engine` (verified by dedicated tests in every chunk, plus
manual source-level scans). No endpoint in the extended research API
accepts a POST, PUT, or DELETE — every route is GET-only, checked by
`test_all_research_routes_are_get_only`. `PAPER_CANDIDATE`, the
highest status this system can assign, has its trading-authorization
disclaimer written directly into its own reason text, not left to be
inferred. The kill switch and structural live-trading lock built in
Phase 0 are untouched by every one of Phase 10's six chunks.

## Limitations

- Phase 8.1/9/9.1 never saved formal `ResearchExperiment` records —
  their `experiment_ids` in the reconstructed candidates are
  documented synthetic references (e.g.
  `"phase9_1_breakout_lookback20_A_trending_only"`), not real UUIDs.
  Future phases should save proper records from the start so this
  translation step isn't needed again.
- Saturation and priority thresholds (3 candidates, 80% density) are
  documented starting choices, not derived or calibrated values —
  same philosophy as every threshold elsewhere in this project.
- The Scorecard's STATISTICAL and ROBUSTNESS categories are `UNKNOWN`
  for 4 of the 5 reconstructed candidates (only H1 ever got a
  dedicated Phase 8.1-style follow-up) — this accurately reflects
  what evidence exists, not a system limitation to fix, but worth
  knowing when reading `/research/candidates` results.
