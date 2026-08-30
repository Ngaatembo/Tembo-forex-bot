# Phase 15 — Risk Engine & Trading Safety Layer

**This phase does NOT establish profitability.** It establishes that
a validated strategy signal can never automatically become a trade —
it must independently clear risk, sizing, and account-safety checks
first, exactly as the eligibility layers (Phases 10-14) already
require independent evidence before advancing.

## Architecture

Built inside the existing `app/risk_engine/` package (Phase 0's
`kill_switch.py` placeholder — "later phases replace the body of this
function with real checks" — this is that later phase):

- `risk_models.py` — RiskDecision, RiskLimitsConfig, AccountState, PositionSizingDetail
- `position_sizing.py` — instrument-aware sizing
- `stop_validation.py` — never corrects an invalid stop, only rejects
- `account_limits.py` — six independent, fail-closed limit checks
- `risk_engine.py` — the orchestrator implementing the exact Step-10 hierarchy

## Position sizing — the Phase 13 lesson, generalized

Two models: "notional_price_unit" (size = risk_amount / stop_distance,
the same model this entire project's backtesting has used since Phase
4) is the only one currently usable — real broker tick/point specs
don't exist in this project's historical CSV data (Phase 14 confirmed
this honestly with None fields). "tick_based" is implemented and
tested for when real broker metadata exists, but isn't reachable
today. Sizing respects minimum_position_size (rounds down to zero,
never up) and position_increment when available.

## Account-level limits (documented conservative starting points, not
derived from historical profitability)

| Limit | Default |
|---|---|
| Max risk per trade | 1% of equity |
| Max total open risk | 3% of equity |
| Max daily loss | 3% -- triggers DO_NOT_TRADE |
| Max drawdown | 15% -- triggers DO_NOT_TRADE |
| Max simultaneous positions | 3 |
| Max notional exposure | 50% of equity |

## The safety hierarchy -- exactly as specified, sequential, no override

```
KILL SWITCH -> ACCOUNT DATA VALID? -> VALIDATED STRATEGY? ->
INSTRUMENT DATA VALID? -> STOP VALID? -> PER-TRADE RISK ->
TOTAL OPEN RISK -> DAILY LOSS -> DRAWDOWN -> POSITION LIMIT ->
EXPOSURE LIMIT -> APPROVED
```

Each stage is a separate early-return in evaluate_risk() -- not a
scored/weighted combination. A later stage can never override an
earlier rejection; proven directly by
test_later_check_never_overrides_earlier_rejection (kill switch
active AND account data also broken -> still reports KILL_SWITCH_ACTIVE,
the first failure in the hierarchy, not the last).

## "PROMISING" != tradeable -- enforced structurally, not by convention

A candidate reaches the risk engine's "VALIDATED STRATEGY?" stage via
Phase 14's Selector. Only status == "TRADEABLE" (Research Gate
PAPER_CANDIDATE) passes; everything else -- including
PROMISING_NOT_TRADEABLE, XAU/USD Breakout's actual current status --
is rejected as NO_VALIDATED_EDGE before any risk or position-sizing
calculation even runs. Proven directly against real data in the
demonstration (Scenario B below).

## A real bug caught during testing (a test's own scenario, not a code bug)

My first "Scenario C should be APPROVED" test used a $20 stop on
$1,900 gold. The risk-based position size (5 units, correctly
computed to risk exactly 1% of equity) produced $9,500 notional --
95% of equity, correctly rejected by the exposure check. This was
the exposure limit working correctly, not a bug: risk-based sizing
on a tight stop can still produce oversized notional exposure on an
expensive instrument. Fixed by widening the test's stop to $40 (also
more realistic for gold's actual volatility), which keeps both risk%
and exposure% within limits -- investigated before treating it as a
test-only fix, not blindly adjusted to force a pass.

## Demonstration -- real data for A and B, explicitly-labeled test-only for C

| Scenario | Selector status | Risk decision |
|---|---|---|
| A: EUR/USD 1H | NO_VALIDATED_EDGE (real) | NO_VALIDATED_EDGE |
| B: XAU/USD 1H Breakout | PROMISING_NOT_TRADEABLE (real) | NO_VALIDATED_EDGE -- never APPROVED |
| C: TEST/ONLY fixture | TRADEABLE (fabricated, clearly labeled) | APPROVED, risk 1.00% |

Scenario C's instrument (TEST/ONLY) and candidate ID
(vsc_test_only_demo) are deliberately unmistakable as non-real --
this is a risk-engine capability demonstration, not a claim that
anything is ready to trade. Full output in
research/results/phase_15_risk_engine_demo.json.

## Costs and slippage

Per-trade risk is computed from entry/stop prices only -- spread and
slippage are not yet folded into the sizing calculation itself
(they're already modeled separately in the backtesting engine's cost
tiers, Phase 4 onward). This is a real, honest gap for actual paper/
live execution: a filled price will differ from the requested entry
by spread/slippage, which would shift the realized risk slightly from
what's calculated here. Documented as a known limitation, not silently
assumed away.

## Security boundary

Zero imports of, or references to, the execution/broker layer
anywhere in app/risk_engine/ -- verified by a dedicated test scanning
every file, plus a second test confirming RiskDecision has no
execute/place_order/send method. One false positive caught in my
own docstring (mentioning a future broker connection in prose,
tripping the token scanner) -- reworded, same pattern as prior phases'
false-positive fixes, not a real gap.

## Future execution-integration boundary (documented only, nothing built)

```
Research -> Strategy Selector -> Risk Engine (this phase) ->
Paper Trading (not built) -> Validation (not built) ->
Execution Adapter (not built) -> Broker (not connected)
```

When execution eventually exists, it must never be able to bypass:
risk limits, candidate eligibility, evidence requirements, the kill
switch, position sizing, or audit logging. The RiskDecision object
this phase produces is designed to BE that audit record -- every field
needed to reconstruct why a decision was made is already present.

## Tests

36 new in test_phase15_risk_engine.py (position sizing across
instruments/scales/constraints, stop validation, all six account
limits independently, and the full hierarchy -- kill switch, missing
account data, NO_VALIDATED_EDGE, the critical PROMISING-not-approved
case, invalid stops, the one genuinely-approved scenario, hierarchy
ordering, determinism, reproducibility, auditability) + 2 security
tests. Full regression: 434/434 (396 unchanged + 38 new).

## Recommendation

Not decided automatically, per instruction. The Risk Engine is
complete and independently verified -- no strategy, including XAU/USD
Breakout, can reach a trade through it without first reaching
PAPER_CANDIDATE. Whatever comes next is your call.
