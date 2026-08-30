# Phase 14 — Generalized Strategy Selection & Market/Timeframe Adaptation

**REAL DEMONSTRATION**, built entirely from existing Phase 10/13/13.1
research artifacts — no new backtests.

## Why this phase exists

Phase 13.1 found the strongest evidence this project has produced —
but it's evidence for exactly one instrument/timeframe/strategy
combination. The actual objective was never "find one good XAU/USD
strategy" — it's a system that, given any instrument/timeframe, can
say either "here's what's validated" or "there's nothing here yet,"
and never silently defaults to trading just because a strategy exists
somewhere in the codebase.

## What was built

### 1. `ValidatedStrategyConfig` (`app/research/validated_strategy_config.py`)

Immutable. References an existing `StrategyCandidate` by ID — never
copies experiment data. Bridges "which researched candidate" with
"for which specific instrument/timeframe/parameter configuration,"
since Phase 10's `StrategyCandidate` deliberately doesn't carry
instrument/timeframe at all. Carries a read-only snapshot of
`gate_status`, `verdict`, and `statistical_level` — nothing in this
object has an `execute()` method or any path to the execution layer.
A `PAPER_CANDIDATE` gate status recorded here still means exactly
what Phase 10 always meant by it: a human may consider a separate
paper-trading decision, never automatic authorization.

### 2. Instrument/Timeframe Adapter (`app/research/instrument_adapter.py`)

Computes what's honestly derivable from historical OHLC data (mean
price, price precision, and — generalizing Phase 13.1's exact hand
derivation into tested infrastructure — notionally-comparable position
sizing across instruments). Explicitly reports `None`, never a
fabricated number, for what historical CSV data cannot provide: tick
size, tick value, point value, minimum position size — real broker
contract specs that would need a broker/data-vendor API this project
doesn't have.

`compute_notionally_comparable_position_size()` is regression-tested
against Phase 13's real derived value (`8.298216860650118` for
XAU/USD) — proving the generalized function reproduces the exact
number that was previously hand-computed once, ad hoc.

### 3. Strategy Selector (`app/research/strategy_selector.py`)

Deterministic, read-only. The core design decision: selection is
driven entirely by Research Gate rank, never by "which config had the
highest historical profit factor." A `REJECT_EARLY` config is never
preferred over a `PROMISING` one regardless of what raw numbers might
suggest — the gate status already encodes everything the evidence
supports.

Four possible outcomes:
- **`TRADEABLE`** — a matching config reached `PAPER_CANDIDATE`
- **`PROMISING_NOT_TRADEABLE`** — matches, but gate stops at `PROMISING`
- **`RESEARCH_REQUIRED`** — matches, but gate is `RESEARCH`/`ROBUSTNESS_REQUIRED`
- **`NO_VALIDATED_EDGE`** — no matching config, or every match rejected/regime-incompatible

**`NO_VALIDATED_EDGE` is a success state**, not an error — the whole
point of this phase.

Regime compatibility is checked directly: if the current regime has
zero observed trades in a config's own evidence, that config is
excluded from eligibility for that regime, with the exclusion reason
recorded explicitly.

## Demonstration — real results, not fabricated

Built from Phase 10's real reconstructed EUR/USD candidates, Phase
13's real GBP/USD results, and Phase 13.1's real XAU/USD robustness
data:

| Instrument | Status | Selected |
|---|---|---|
| EUR/USD 1H | `NO_VALIDATED_EDGE` | none (5 configs considered, all REJECT_EARLY/CLOSED) |
| GBP/USD 1H | `NO_VALIDATED_EDGE` | none (3 configs considered, all REJECT_EARLY/CLOSED) |
| XAU/USD 1H | `PROMISING_NOT_TRADEABLE` | breakout lookback=30 (all 3 lookbacks PROMISING) |

**XAU/USD is never reported as `TRADEABLE`**, exactly matching Phase
13.1's real evidence (statistical category still `WEAK`). The
research recommendation for XAU/USD is generated directly from that
gap: "Grow the out-of-sample statistical sample... before this can
advance past PROMISING." Full output in
`research/results/phase_14_strategy_selection_demo.json`.

## Generalization work (Steps 4-5, infrastructure only, no tuning)

Confirmed and documented (not re-litigated — Phase 13.1 already found
these):
- Breakout's core mechanism and ATR-stop multiple are scale-relative
  by construction — transfer cleanly.
- Position sizing required correction — now generalized (above).
- Lookback values and `max_holding_candles` are candle counts, not
  time durations — genuinely timeframe-relative, not yet normalized
  into a time-based representation. Not fixed this phase — Step 4
  asked for correct semantics to be identified, not implemented; doing
  so would mean touching strategy parameters, which this phase's own
  scope explicitly excludes ("do not optimize these values yet").

## Architecture audit — what exists vs. what's still missing

**Exists and reusable:** the full research pipeline through
`StrategyCandidate`, a proven 3-instrument import pattern, the
Instrument/Timeframe Adapter (new this phase), the deterministic
Selector (new this phase), and a structurally-locked execution
boundary verified by dedicated tests in every phase since Phase 7 —
now including this one.

**Still missing, identified but not built (correctly, per instruction):**
- A live regime-detection feed (the Selector's `current_regime`
  parameter exists and is tested, but nothing yet supplies "what
  regime is the market in right now" — that's real-time data
  infrastructure, not research infrastructure)
- Risk infrastructure beyond `RiskConfig`'s still-unused percent-sizing
- Any MT5/broker adapter (see boundary below — correctly absent)
- Paper trading infrastructure

## Step 8 — XAU/USD Breakout represented honestly, not promoted

All three lookbacks (30/40/50) are represented in the demonstration
exactly as Phase 13.1 found them: `PROMISING`, robustness passed,
`statistical_level: WEAK`, `regime_evidence` showing concentration in
`HIGH_VOLATILITY`. The architecture makes it structurally impossible
for this to read as `TRADEABLE` — the Selector's own gate-rank table
maps `PROMISING` to `PROMISING_NOT_TRADEABLE`, never to `TRADEABLE`,
and only `PAPER_CANDIDATE` (a status this candidate has never reached)
maps to `TRADEABLE`. This isn't a runtime check that could be
bypassed — it's the only mapping the rank table defines.

## Step 11 — Future MT5 integration boundary (design only, not built)

```
Research Engine (Phases 0-14, this phase's Selector included)
        |
Strategy Selection Engine  <- built this phase, read-only
        |
Risk Engine  <- NOT YET BUILT (RiskConfig exists, unused)
        |
Paper Trading  <- NOT YET BUILT
        |
Validation (does paper performance match research evidence?)
        |
MT5 Execution Adapter  <- NOT YET BUILT, NOT YET DESIGNED IN DETAIL
        |
Broker
```

The research layer must never call the execution layer directly —
already true and verified (`test_phase14_strategy_selection_has_no_execution_or_broker_dependency`,
alongside every equivalent test since Phase 7). When an execution
layer eventually exists, it must never be able to bypass: risk limits,
candidate eligibility (only `TRADEABLE` results, never
`PROMISING_NOT_TRADEABLE` or below), evidence requirements, the kill
switch, position sizing, or audit logging. None of this is built yet —
documented as a boundary for later, not implemented now.

## Tests

24 new (config validation/immutability/serialization, instrument
adapter including the Phase 13 regression check, and the full selector
behavior matrix — paper-candidate tradeable, promising-not-tradeable,
rejected exclusion, no-configs case, research-required, regime
incompatibility, instrument/timeframe mismatch exclusion, the
never-pick-by-PF guarantee, auditability, determinism) + 1 security
test. Full regression: 396/396 (371 unchanged + 25 new).

## Bugs / false positives found

One false-positive in my own manual security grep (a docstring
mentioning "app.execution" in prose, not code) — investigated,
confirmed the actual pytest security test's token list didn't
overlap with my ad-hoc grep's broader list, reworded the docstring
for clarity regardless (same pattern as prior phases' false-positive
fixes). Not a real gap; both the strict and loose scans are clean now.

## Recommendation

Not decided automatically, per instruction. Two independent paths
forward exist and don't need to be resolved together: (1) continue
growing XAU/USD Breakout's statistical evidence, or (2) begin the
still-missing general-engine infrastructure (live regime feed, real
Risk Engine) independent of any specific strategy's status. Neither
is started here. Your call.
