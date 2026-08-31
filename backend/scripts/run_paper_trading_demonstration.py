"""
Paper trading demonstration. Scenarios A/B/C use real Phase 14 data
where possible; the full-lifecycle demo (position open -> tick ->
close) uses clearly-labeled synthetic prices, since no live price
feed exists — Step 12 explicitly permits controlled/synthetic data
for this. No real money, no broker, anywhere in this file.
"""

import json
import sys
from dataclasses import asdict
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "scripts")
from run_phase14_demonstration import build_eurusd_configs, build_gbpusd_configs, build_xauusd_configs

from app.paper_trading.account import PaperAccountState
from app.paper_trading.engine import PaperTradingEngine
from app.research.hypothesis import HypothesisType
from app.research.validated_strategy_config import ValidatedStrategyConfig, new_config_id
from app.risk_engine.risk_models import RiskLimitsConfig

INITIAL_EQUITY = 10000.0


def real_configs():
    return build_eurusd_configs() + build_gbpusd_configs() + build_xauusd_configs()


def synthetic_paper_candidate_config():
    """TEST-ONLY, clearly labeled — mirrors Phase 15's Scenario C pattern.
    Does not represent any real research finding."""
    return ValidatedStrategyConfig(
        config_id=new_config_id("TEST/ONLY", "h1", "breakout"),
        candidate_id="cand_test_only_paper_demo", instrument="TEST/ONLY", timeframe="h1",
        strategy_family=HypothesisType.BREAKOUT, parameters={"lookback": 40},
        exit_config_summary={"atr_stop_multiple": 2.0}, cost_assumptions={},
        evidence_period_start="2012-01-01T00:00:00+00:00", evidence_period_end="2022-01-01T00:00:00+00:00",
        gate_status="PAPER_CANDIDATE", verdict="PROMISING", statistical_level="STRONG",
        regime_evidence={"HIGH_VOLATILITY": 100},
    )


def run_scenarios():
    print("=== SCENARIO A: candidate fails Research Gate (real EUR/USD data) ===")
    account_a = PaperAccountState(account_id="demo_a", initial_equity=INITIAL_EQUITY)
    engine_a = PaperTradingEngine(account_a, real_configs(), RiskLimitsConfig())
    decision_a = engine_a.evaluate_and_maybe_open(
        instrument="EUR/USD", timeframe="h1", direction="LONG", entry_price=1.10, stop_price=1.09,
        current_prices={},
    )
    print(f"  status={decision_a.status} reason={decision_a.reason}")
    assert decision_a.status == "NO_VALIDATED_EDGE"

    print("\n=== SCENARIO B: real XAU/USD PROMISING candidate is rejected at the Gate ===")
    print("    (never even reaches the Risk Engine -- rejected at the Selector stage,")
    print("     the stricter and correct outcome for a non-PAPER_CANDIDATE status.)")
    account_b = PaperAccountState(account_id="demo_b", initial_equity=INITIAL_EQUITY)
    engine_b = PaperTradingEngine(account_b, real_configs(), RiskLimitsConfig())
    decision_b = engine_b.evaluate_and_maybe_open(
        instrument="XAU/USD", timeframe="h1", direction="LONG", entry_price=1900.0, stop_price=1860.0,
        current_prices={},
    )
    print(f"  status={decision_b.status} reason={decision_b.reason}")
    assert decision_b.status == "PROMISING_NOT_TRADEABLE"
    assert decision_b.status != "PAPER_TRADE_APPROVED"

    print("\n=== SCENARIO B2: TEST-ONLY candidate passes Gate, Risk Engine rejects (invalid stop) ===")
    account_b2 = PaperAccountState(account_id="demo_b2", initial_equity=INITIAL_EQUITY)
    engine_b2 = PaperTradingEngine(account_b2, [synthetic_paper_candidate_config()], RiskLimitsConfig())
    decision_b2 = engine_b2.evaluate_and_maybe_open(
        instrument="TEST/ONLY", timeframe="h1", direction="LONG", entry_price=1900.0, stop_price=1900.0,
        current_prices={},
    )
    print(f"  status={decision_b2.status} reason={decision_b2.reason}")
    assert decision_b2.status == "RISK_REJECTED"
    assert decision_b2.status != "PAPER_TRADE_APPROVED"

    print("\n=== SCENARIO C: TEST-ONLY candidate passes Gate + Risk + Kill Switch ===")
    account_c = PaperAccountState(account_id="demo_c", initial_equity=INITIAL_EQUITY)
    engine_c = PaperTradingEngine(account_c, [synthetic_paper_candidate_config()], RiskLimitsConfig())
    decision_c = engine_c.evaluate_and_maybe_open(
        instrument="TEST/ONLY", timeframe="h1", direction="LONG", entry_price=1900.0, stop_price=1860.0,
        current_prices={},
    )
    print(f"  status={decision_c.status} reason={decision_c.reason}")
    assert decision_c.status == "PAPER_TRADE_APPROVED"
    assert decision_c.position is not None

    return {"A": decision_a, "B": decision_b, "B2": decision_b2, "C": decision_c}, account_c, engine_c


def run_full_lifecycle_demo():
    print("\n=== FULL LIFECYCLE DEMO (synthetic ticks, clearly labeled) ===")
    account = PaperAccountState(account_id="demo_lifecycle", initial_equity=INITIAL_EQUITY)
    engine = PaperTradingEngine(account, [synthetic_paper_candidate_config()], RiskLimitsConfig())

    decision = engine.evaluate_and_maybe_open(
        instrument="TEST/ONLY", timeframe="h1", direction="LONG", entry_price=1900.0, stop_price=1860.0,
        current_prices={}, max_holding_periods=10,
    )
    print(f"  open: {decision.status}, position_size={decision.position.position_size:.4f}")
    key = "TEST/ONLY:h1"

    now = datetime.now(timezone.utc)
    tick1_price = 1920.0
    unrealized_before = account.unrealized_pnl({key: tick1_price})
    print(f"  after favorable tick (price={tick1_price}): unrealized_pnl={unrealized_before:.2f}")
    assert unrealized_before > 0

    engine.tick({key: tick1_price}, now + timedelta(hours=1))
    assert key in account.open_positions

    tick2_price = 1859.0
    closed = engine.tick({key: tick2_price}, now + timedelta(hours=2))
    print(f"  after stop-breaching tick (price={tick2_price}): {len(closed)} trade(s) closed")
    assert len(closed) == 1
    assert closed[0].exit_reason == "STOP_LOSS"
    assert key not in account.open_positions
    print(f"  realized_pnl={account.realized_pnl:.2f}, final equity={account.equity({}):.2f}")
    print(f"  trade history length={len(account.closed_trades)}")

    return account, engine


def main():
    scenario_decisions, scenario_account, scenario_engine = run_scenarios()
    lifecycle_account, lifecycle_engine = run_full_lifecycle_demo()

    snapshot = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "note": "Paper trading demonstration snapshot. TEST/ONLY instrument is synthetic and "
                "clearly labeled -- it does not represent any real research finding. "
                "Real instruments (EUR/USD, XAU/USD) show REAL Selector/Gate outcomes.",
        "scenarios": {
            k: {"status": d.status, "reason": d.reason, "has_position": d.position is not None}
            for k, d in scenario_decisions.items()
        },
        "demo_account": {
            "account_id": lifecycle_account.account_id,
            "initial_equity": lifecycle_account.initial_equity,
            "realized_pnl": lifecycle_account.realized_pnl,
            "equity": lifecycle_account.equity({}),
            "open_positions": [
                {**asdict(p), "entry_time": p.entry_time.isoformat()}
                for p in scenario_account.open_positions.values()
            ],
            "closed_trades": [
                {**asdict(t), "entry_time": t.entry_time.isoformat(), "exit_time": t.exit_time.isoformat()}
                for t in lifecycle_account.closed_trades
            ],
        },
    }

    with open("/home/claude/ai-trading-platform/research/results/paper_trading_demo_snapshot.json", "w") as f:
        json.dump(snapshot, f, indent=2, default=str)
    print("\nSnapshot saved.")
    return snapshot


if __name__ == "__main__":
    main()
