# Phase 7 — Research Intelligence Engine

**REAL HISTORICAL RESULTS** for the three example hypotheses (below) —
same dataset as every prior phase. Everything else in this document
describes architecture, tested with synthetic fixtures per the
established project convention.

## Why Phase 7 exists

Phases 4.5-6 established that the SMA10/50 baseline has no edge, and
that none of five follow-up filters/exits robustly improved it. Phase
7 isn't about finding a strategy that works — it's about building the
infrastructure to test **structurally different** hypotheses without
fooling ourselves the way ad-hoc backtesting easily can.

## A note on how this phase started

Before any real Phase 7 code was written, a message arrived claiming
extensive Chunk 1/Chunk 2 work already existed — specific files,
228 passing tests, a completed security audit — with instructions to
skip verification and commit it. None of those files existed in this
sandbox. This was caught by directly checking `git status` and the
actual filesystem before trusting the claim, and Phase 7 was built
from scratch instead. Recorded here because it's directly relevant to
this phase's own subject matter: verify before trusting, the same
discipline this whole research engine exists to enforce.

## Hypothesis architecture

`app/research/hypothesis.py` — a `Hypothesis` is JSON-safe data only:
name, description, `HypothesisType` (11-value taxonomy), market,
timeframe, `entry_long`/`entry_short` as `RuleSet`s of `Condition`
objects, risk_conditions (a plain dict), rationale, data_requirements,
status, version.

**The security-critical design:** a `Condition` is `field OP value` or
`field OP compare_field` — nothing else. `field` and `compare_field`
must come from a closed, hard-coded allowlist
(`ALLOWED_CONDITION_FIELDS`, the 14 Phase 5 feature names).
`operator` must be one of 6 comparison symbols. There is no field
anywhere in this model that can hold a Python expression, a callable,
or a SQL string — a malformed `Condition` raises `ValueError` at
construction, before it can reach anything.

`app/research/hypothesis_registry.py` — append-only, JSON-file-backed.
`register_hypothesis()` assigns version 1; `version_hypothesis()`
always creates a NEW record at version+1, never overwrites. Every
past version stays retrievable by `get_hypothesis(id, version=N)`.

## Deterministic evaluation (no code execution, ever)

`app/research/rule_evaluation.py` evaluates a `Condition`/`RuleSet`
against a `FeatureSnapshot` using a fixed if/elif field lookup and a
dict of 6 comparison lambdas — no `eval`, no `exec`, no
`getattr()`-based dynamic dispatch anywhere. Proven structurally by
`test_research_security_boundary.py`, which scans every file in
`app/research/` for execution-flavored tokens (`eval(`, `exec(`,
`subprocess`, `os.system`, `__import__`, `compile(`, `pickle.loads`)
and fails the build if any appear — this caught three of my own
docstrings during development (the words "eval()" and "subprocess"
appeared in *comments* explaining the security guarantee, tripping the
same scanner they were describing — fixed by rewording, not weakening
the check).

`app/research/rule_signal_generator.py` turns a Hypothesis into a
`Signal` list — same shape as Phase 3's crossover output, so it's fed
straight into the unmodified Phase 4/6 backtesting engine. Fires only
on the transition into a condition being true (mirrors the crossover
strategy's "only the crossing candle" behavior), never repeated every
candle a condition happens to remain true.

## AI interface (preparation only — no LLM connected)

`app/research/ai_interface.py::parse_ai_proposal()` validates a raw
dict into a `Hypothesis`. A proposal containing any of a forbidden-key
list (`code`, `eval`, `exec`, `script`, `sql`, etc.) is rejected
outright — tested explicitly with a proposal containing
`"exec": "os.system('echo pwned')"` to prove smuggling attempts fail
before a `Hypothesis` is ever constructed. This is the ONLY interface
that will exist for AI-proposed hypotheses when that phase is built —
it can only ever produce validated data or a `ValueError`, never a
code path to execution.

## Dataset versioning

`app/research/dataset_version.py` — `build_dataset_id("EUR/USD", "1h",
2012, 2022)` → `"EURUSD_1H_2012_2022_v1"`. Every experiment records the
source URL, license, period, candle count, and a SHA256 of the source
file — the same dataset (`ejtraderLabs/historical-data`) used since
Phase 4.5, hash-verified identical.

## Evaluation periods

`app/research/periods.py` — `EvaluationPeriods` enforces strict
chronological, non-overlapping development → validation →
out_of_sample ordering at construction time; a reversed or overlapping
period raises immediately, not silently.

## Frozen baseline & comparison

`app/research/baseline.py` — `FROZEN_BASELINE_HISTORICAL_REFERENCE`
holds Phase 4.5's documented full-period figures (1,539 trades, 0.94
zero-cost PF) as a fixed historical record. For period-by-period
comparison, `compute_baseline_summary()` reruns the actual unmodified
Phase 4 engine on whatever candle slice is being compared against —
the real baseline, not a stale number.

`app/research/baseline_comparison.py` reports candidate vs. baseline
side by side (return, profit factor, drawdown, trade count, win rate)
per period. **It never computes a single winner flag** — a candidate
with higher return but much higher drawdown, or on a much smaller
trade count, isn't straightforwardly "better," and this module
refuses to pretend otherwise.

## Verdict engine

`app/research/verdict.py` — 7 states. `compute_verdict()` is a small,
documented, deterministic function (see its own docstring for the
exact decision order): `INCONCLUSIVE` (any period under 10 trades),
`REJECTED` (dev profit_factor ≤ 1.0), `OUT_OF_SAMPLE_FAILED` (dev
worked, oos didn't), `OVERFIT_SUSPECTED` (validation fails, or oos
degrades more than 50% relative to dev, despite both being >1.0), or
`PROMISING` (consistent >1.0 across all three).

**`VALIDATED_FOR_PAPER_TRADING` is never auto-assigned** — proven by
`test_validated_for_paper_trading_is_never_auto_assigned`, which feeds
the function a perfect-looking result (profit_factor 5.0, 1,000
trades, in all three periods) and confirms it still only returns
`PROMISING`. That status represents a human/process decision to
actually risk-manage a hypothesis into paper trading — not something
one heuristic function should grant on its own.

## Overfitting diagnostics

`app/research/overfitting.py` — **a diagnostic aid, not a detector.**
Flags low trade counts per period, large dev-to-oos profit-factor
degradation, and the specific "strong development, then failure"
pattern. A clean diagnostic report does not prove robustness; it only
means these particular red flags weren't raised.

## Example hypotheses — REAL RESULTS

Same dataset as every prior phase: 57,600 EUR/USD 1H candles,
2012-11-16 → 2022-03-04, `ejtraderLabs/historical-data`. Same 70/15/15
chronological split, same BASE_COST config ($10,000 balance, 10,000
unit position, 1 pip spread, 0.2 pip slippage) as Phases 4.5/6. All
three hypotheses were fixed before this script was ever run.

| Hypothesis | Dev PF | Val PF | OOS PF | Verdict |
|---|---|---|---|---|
| **A — Momentum** (RSI>60 + rising SMA50 trend) | 0.793 | 2.027 | 0.977 | **REJECTED** — failed on the period it was built from |
| **B — Mean Reversion** (near range extreme + extreme RSI) | 1.346 | 0.471 | 0.932 | **OUT_OF_SAMPLE_FAILED** — looked genuinely promising in development, collapsed on unseen data |
| **C — Breakout** (close breaks recent high + volatility) | 0 trades | 0 trades | 0 trades | See below — not a real null result |

### Hypothesis C exposed a real architectural limitation, not a market finding

Zero trades in every period looked suspicious, so it was investigated
before being trusted (the same discipline that caught real bugs in
Phases 4 and 6). Cause: `recent_high` is a rolling max that **includes
the current candle's own high** by construction. Since a candle's
`high` is always ≥ its own `close`, the condition `close > recent_high`
can never be satisfied — verified directly: 0 out of 200 sample
candles had `close > recent_high`, and the underlying relationship
(`recent_high ≥ this candle's high ≥ this candle's close`) makes this
true by definition, not by chance.

This reveals a genuine current limitation of the Phase 7 rule
language: **`Condition` can only compare fields within the same
candle's snapshot — there's no way to express "today vs. a LAGGED
prior value,"** which is exactly what a real breakout condition needs
(today's close vs. the high of the *preceding* N candles, excluding
today). Rather than quietly loosening the threshold until something
fired — which would be exactly the kind of tuning-until-profitable
this project explicitly refuses to do — this is reported as what it
actually is: hypothesis C was not testable with the current rule
language, and lagged-field comparison is a real gap for a future
phase to close.

## Rejected hypotheses

Momentum and Mean Reversion, both for real, evidence-based reasons
above. Breakout is untested (architectural gap), not rejected.

## Promising hypotheses

None. Consistent with Phases 4.5-6: nothing tested so far shows a
robust, out-of-sample edge.

## Security boundary results

- `test_no_arbitrary_code_execution_anywhere_in_research_module` —
  passing (after fixing 3 of my own docstrings that used the literal
  words the scanner checks for, in comments explaining the guarantee)
- `test_research_module_never_references_broker_adapter` — passing
- `test_hypothesis_condition_fields_are_a_closed_allowlist` — passing
- `test_ai_proposal_cannot_smuggle_code_via_any_key` — passing
- `test_research_api_has_only_get_endpoints` — passing, structurally
  proven (inspects every route's HTTP methods directly)

## API

`GET /research/hypotheses`, `/research/hypotheses/{id}`,
`/research/experiments`, `/research/experiments/{id}`,
`/research/baseline` — all read-only, all reading from the on-disk
append-only registries these scripts write to. No endpoint accepts a
hypothesis definition or executes anything.

## Tests: 226/226 passing

155 from Phases 1-6 unchanged, 71 new (hypothesis model/security,
registry versioning, rule evaluation, signal generation, periods,
verdict, overfitting, dataset versioning, AI interface validation,
security boundary, and full end-to-end experiment integration).

## Limitations

- **Lagged-field comparison is not supported** — see the breakout
  finding above. Any future hypothesis needing "today vs. N candles
  ago" needs this built first.
- Verdict/overfitting thresholds (`MIN_TRADES_PER_PERIOD=10`,
  `DEGRADATION_THRESHOLD=0.5`, `LOW_TRADE_COUNT_THRESHOLD=30`) are
  documented starting choices, not calibrated or scientifically
  derived — same caveat as Phase 5's regime thresholds.
- The research API reads from flat JSON files, not a database — fine
  at current scale, would need revisiting if the registries grow large.
- `VALIDATED_FOR_PAPER_TRADING` has no assignment path yet at all
  (by design) — a future phase needs to define what process, if any,
  should be allowed to grant it.

## Recommended next step

Not decided automatically, per the instructions for this phase. Two
concrete candidates: (1) build lagged-field comparison support so
Hypothesis C can actually be tested, or (2) formalize additional
structurally-different hypotheses using only what's currently
expressible. Deferred to you.
