"""
Phase 14 demonstration — builds real ValidatedStrategyConfig records
from Phase 10/13/13.1's actual saved research artifacts (no new
backtests) and runs the selector against three real instrument/
timeframe pairs, proving it does NOT simply pick the highest PF.
"""

import json

from app.research.hypothesis import HypothesisType
from app.research.strategy_selector import select_strategy
from app.research.validated_strategy_config import ValidatedStrategyConfig, new_config_id

RESULTS_DIR = "/home/claude/ai-trading-platform/research/results"


def _load(name):
    with open(f"{RESULTS_DIR}/{name}") as f:
        return json.load(f)


def build_eurusd_configs():
    candidates = _load("phase_10_strategy_candidates.json")
    configs = []
    family_map = {
        "H1 — Range-Extreme Mean Reversion": HypothesisType.MEAN_REVERSION,
        "H2 — Volatility Squeeze Breakout": HypothesisType.VOLATILITY,
        "Market-Structure Breakout (lookback=20)": HypothesisType.BREAKOUT,
        "Market-Structure Breakout (lookback=40)": HypothesisType.BREAKOUT,
        "Market-Structure Breakout (lookback=60)": HypothesisType.BREAKOUT,
    }
    for c in candidates:
        family = family_map.get(c["name"])
        if family is None:
            continue
        configs.append(ValidatedStrategyConfig(
            config_id=new_config_id("EUR/USD", "h1", family.value),
            candidate_id=c["candidate_id"], instrument="EUR/USD", timeframe="h1",
            strategy_family=family, parameters={}, exit_config_summary={},
            cost_assumptions={"tier": "BASE"},
            evidence_period_start="2012-11-16T00:00:00+00:00", evidence_period_end="2022-03-04T23:00:00+00:00",
            gate_status=c["gate_status"], verdict=c["verdict"] or "UNKNOWN",
            statistical_level="UNKNOWN", regime_evidence={},
        ))
    return configs


def build_gbpusd_configs():
    from app.research.verdict import compute_verdict
    from app.research.overfitting import compute_overfitting_diagnostics
    from app.research.scorecard import compute_scorecard
    from app.research.research_gate import compute_research_gate
    from app.backtesting.models import BacktestSummary

    data = _load("phase_13_multimarket_results.json")
    configs = []
    family_map = {"H1": HypothesisType.MEAN_REVERSION, "Breakout40": HypothesisType.BREAKOUT, "Momentum_T1_60": HypothesisType.MOMENTUM}
    for strat_name, family in family_map.items():
        strat_data = data["GBP/USD"][strat_name]
        base = {l: BacktestSummary(**strat_data["BASE"][l]) for l in ("development", "validation", "out_of_sample")}
        verdict = compute_verdict(**base)
        overfitting = compute_overfitting_diagnostics(**base)
        scorecard = compute_scorecard(base, verdict, overfitting)
        gate = compute_research_gate(verdict, scorecard, overfitting)
        configs.append(ValidatedStrategyConfig(
            config_id=new_config_id("GBP/USD", "h1", family.value),
            candidate_id=f"gbpusd_{strat_name.lower()}", instrument="GBP/USD", timeframe="h1",
            strategy_family=family, parameters={}, exit_config_summary={},
            cost_assumptions={"tier": "BASE"},
            evidence_period_start="2012-11-16T00:00:00+00:00", evidence_period_end="2022-03-04T23:00:00+00:00",
            gate_status=gate.status, verdict=verdict.value,
            statistical_level=scorecard.statistical.level, regime_evidence={},
        ))
    return configs


def build_xauusd_configs():
    data = _load("phase_13_1_xauusd_robustness.json")
    configs = []
    for lookback_str, lb_data in data.items():
        regime_evidence = {k: v["trade_count"] for k, v in lb_data["regime_breakdown"].items()}
        configs.append(ValidatedStrategyConfig(
            config_id=new_config_id("XAU/USD", "h1", f"breakout_{lookback_str}"),
            candidate_id=f"xauusd_breakout_{lookback_str}", instrument="XAU/USD", timeframe="h1",
            strategy_family=HypothesisType.BREAKOUT, parameters={"lookback": int(lookback_str)},
            exit_config_summary={"atr_stop_multiple": 2.0, "max_holding_candles": 100},
            cost_assumptions={"tier": "BASE"},
            evidence_period_start="2012-11-16T00:00:00+00:00", evidence_period_end="2022-03-04T23:00:00+00:00",
            gate_status=lb_data["gate"]["status"], verdict=lb_data["verdict_base_cost"],
            statistical_level=lb_data["scorecard"]["statistical"]["level"], regime_evidence=regime_evidence,
        ))
    return configs


def main():
    all_configs = build_eurusd_configs() + build_gbpusd_configs() + build_xauusd_configs()
    print(f"Built {len(all_configs)} real ValidatedStrategyConfig records from existing research.\n")

    for instrument in ("EUR/USD", "GBP/USD", "XAU/USD"):
        result = select_strategy(instrument, "h1", all_configs)
        print(f"=== {instrument} 1H ===")
        print(f"  status: {result.status}")
        print(f"  reason: {result.reason}")
        print(f"  considered: {len(result.considered)} config(s)")
        for c in result.considered:
            print(f"    - {c.config_id}: {c.gate_status} — {c.reason}")
        if result.research_recommendation:
            print(f"  research_recommendation: {result.research_recommendation}")
        print()

    return all_configs


if __name__ == "__main__":
    main()
