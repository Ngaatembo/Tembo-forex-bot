"""
Phase 15 demonstration — three scenarios, reusing Phase 14's real
selection results (no fabricated tradeable scenario except the
explicitly-labeled test-only Scenario C).
"""

import sys

sys.path.insert(0, "scripts")

from run_phase14_demonstration import main as phase14_main

from app.research.instrument_adapter import InstrumentTimeframeInfo
from app.research.strategy_selector import ConsideredCandidate, SelectionResult, select_strategy
from app.risk_engine.risk_engine import evaluate_risk
from app.risk_engine.risk_models import AccountState, RiskLimitsConfig


def good_account():
    return AccountState(
        equity=10000.0, peak_equity=10000.0, daily_start_equity=10000.0,
        daily_realized_pnl=0.0, daily_unrealized_pnl=0.0, open_positions_count=0,
        total_open_risk_pct=0.0, kill_switch_active=False,
    )


def main():
    all_configs = phase14_main()
    limits = RiskLimitsConfig()

    print("\n" + "=" * 60)
    print("SCENARIO A - EUR/USD 1H (no validated candidate)")
    print("=" * 60)
    selection = select_strategy("EUR/USD", "h1", all_configs)
    decision = evaluate_risk(selection_result=selection, account=good_account(), limits=limits)
    print(f"Selector status: {selection.status}")
    print(f"Risk decision: {decision.state}")
    print(f"Reason: {decision.reason}")
    assert decision.state == "NO_VALIDATED_EDGE"

    print("\n" + "=" * 60)
    print("SCENARIO B - XAU/USD 1H Breakout (PROMISING, not PAPER_CANDIDATE)")
    print("=" * 60)
    selection = select_strategy("XAU/USD", "h1", all_configs)
    xau_info = InstrumentTimeframeInfo("XAU/USD", "h1", mean_price=1900.0, price_precision_decimals=2)
    decision = evaluate_risk(
        selection_result=selection, account=good_account(), limits=limits,
        direction="LONG", entry_price=1900.0, stop_price=1860.0, instrument_info=xau_info,
    )
    print(f"Selector status: {selection.status}")
    print(f"Risk decision: {decision.state}")
    print(f"Reason: {decision.reason}")
    assert decision.state == "NO_VALIDATED_EDGE"
    assert decision.state != "APPROVED"

    print("\n" + "=" * 60)
    print("SCENARIO C - Hypothetical eligible TEST-ONLY candidate")
    print("(This does NOT represent any real research finding -- it exists")
    print(" only to prove the Risk Engine can reach APPROVED when every")
    print(" condition genuinely is satisfied.)")
    print("=" * 60)
    test_only_selection = SelectionResult(
        "TEST/ONLY", "h1", "TRADEABLE", "vsc_test_only_demo",
        "TEST-ONLY: Selected vsc_test_only_demo: gate status PAPER_CANDIDATE.",
        (ConsideredCandidate("vsc_test_only_demo", "PAPER_CANDIDATE", "TEST-ONLY fixture"),), None,
    )
    test_info = InstrumentTimeframeInfo("TEST/ONLY", "h1", mean_price=1900.0, price_precision_decimals=2)
    decision = evaluate_risk(
        selection_result=test_only_selection, account=good_account(), limits=limits,
        direction="LONG", entry_price=1900.0, stop_price=1860.0, instrument_info=test_info,
    )
    print(f"Selector status: {test_only_selection.status}")
    print(f"Risk decision: {decision.state}")
    print(f"Reason: {decision.reason}")
    print(f"Position sizing: {decision.position_sizing}")
    print(f"Computed risk: {decision.computed_risk_pct:.2%}")
    assert decision.state == "APPROVED"

    print("\nAll three scenarios behaved exactly as required.")
    print("This demonstration does NOT authorize live or paper trading.")


if __name__ == "__main__":
    main()
