"""
Phase 8.1 — H1 robustness & statistical validation. DIAGNOSTIC ONLY.

Fresh-data check (documented in docs/phase-8-1-notes.md) found no
genuinely fresh, clearly-licensed EUR/USD 1H data extending past
2022-03-04. Per the pre-registered rule, the OFFICIAL Phase 8 verdict
for H1 therefore remains exactly OUT_OF_SAMPLE_FAILED — nothing in
this script can or does change it. Everything below is diagnostic
analysis on the already-seen out-of-sample data.

H1's rule is imported directly from Phase 8's own script
(build_h1_range_extreme_reversion), never retyped — this guarantees
the rule tested here is byte-identical to the one already recorded,
not a manual transcription that could silently drift.
"""

import sys
sys.path.insert(0, "scripts")

from run_phase8_hypotheses import build_h1_range_extreme_reversion

from app.backtesting.config import BacktestConfig
from app.backtesting.engine_research import simulate_trades_with_exit_rules
from app.backtesting.exit_rules import BASELINE_EXIT
from app.data_engine.importers.ejtrader_source import import_ejtrader_eurusd_h1
from app.data_engine.normalizer import normalize_candles
from app.research.hypothesis import Condition, Hypothesis, HypothesisType, RuleSet, new_hypothesis_id
from app.research.periods import EvaluationPeriod, EvaluationPeriods, split_candles_by_period
from app.research.rule_signal_generator import generate_signals_from_hypothesis
from app.research.statistics_analysis import (
    bootstrap_pnl_confidence_interval, compute_breakeven_win_rate,
    compute_payoff_stats, wilson_confidence_interval,
)
from app.research.trade_analysis import attach_context_to_trades, group_by_regime
from app.technical_engine.features import calculate_feature_snapshots

COST_TIERS = {
    "LOW": {"spread": 0.00005, "slippage": 0.00001},
    "BASE": {"spread": 0.00010, "slippage": 0.00002},
    "HIGH": {"spread": 0.00020, "slippage": 0.00005},
}
ACCOUNT = {"initial_balance": 10000.0, "position_size": 10000.0}

# Pre-registered parameter neighborhood (fixed before this script ran
# against any result) — one parameter varied at a time, original held fixed.
DISTANCE_NEIGHBORHOOD = [0.0004, 0.0005, 0.0006]  # 0.0005 is H1's original
ATR_CEILING_NEIGHBORHOOD = [0.0012, 0.0015, 0.0018]  # 0.0015 is H1's original


def build_variant(distance: float, atr_ceiling: float, label: str) -> Hypothesis:
    """A parameter-neighbor variant of H1 — a SEPARATE hypothesis object
    for robustness testing, never a modification to the original H1."""
    return Hypothesis(
        id=new_hypothesis_id(f"h1_variant_{label}"),
        name=f"H1 variant ({label})", description=f"distance={distance}, atr_ceiling={atr_ceiling}",
        hypothesis_type=HypothesisType.MEAN_REVERSION, market="EUR/USD", timeframe="1h",
        entry_long=RuleSet((
            Condition(field="distance_from_low", operator="<", value=distance),
            Condition(field="atr_percent", operator="<", value=atr_ceiling),
        )),
        entry_short=RuleSet((
            Condition(field="distance_from_high", operator="<", value=distance),
            Condition(field="atr_percent", operator="<", value=atr_ceiling),
        )),
        risk_conditions={"exit_config": "baseline_opposite_signal"},
        rationale=f"Phase 8.1 robustness neighbor of H1: {label}",
        data_requirements=("distance_from_low", "distance_from_high", "atr_percent"),
    )


def run_one(hypothesis, candles, features, cost_key):
    config = BacktestConfig(**ACCOUNT, **COST_TIERS[cost_key])
    signals = generate_signals_from_hypothesis(hypothesis, candles, features)
    return simulate_trades_with_exit_rules(candles, signals, features, config, BASELINE_EXIT)


def summarize(label, result):
    s = result.summary
    pf = f"{s.profit_factor:.3f}" if s.profit_factor is not None else "n/a"
    print(f"  {label:24s}: trades={s.trade_count:5d}  return={s.total_return:8.4f}  pf={pf}")


def main():
    csv_path = "/home/claude/real_data/EURUSDh1.csv"
    print(f"Importing {csv_path} ...")
    candles = normalize_candles(import_ejtrader_eurusd_h1(csv_path))
    print(f"{len(candles)} candles")

    n = len(candles)
    train_end, val_end = int(n * 0.70), int(n * 0.85)
    periods = EvaluationPeriods(
        development=EvaluationPeriod("development", candles[0].timestamp, candles[train_end].timestamp),
        validation=EvaluationPeriod("validation", candles[train_end].timestamp, candles[val_end].timestamp),
        out_of_sample=EvaluationPeriod("out_of_sample", candles[val_end].timestamp, candles[-1].timestamp),
    )
    split = split_candles_by_period(candles, periods)
    features_by_period = {label: calculate_feature_snapshots(c) for label, c in split.items()}

    h1 = build_h1_range_extreme_reversion()
    print(f"\nH1 rule reused, unmodified, id={h1.id}")

    # --- 1. Cost sensitivity: H1 unmodified, all 3 tiers, all 3 periods ---
    print("\n=== COST SENSITIVITY (H1 unmodified) ===")
    cost_sensitivity = {}
    for tier in COST_TIERS:
        cost_sensitivity[tier] = {}
        print(f" {tier}:")
        for label in ("development", "validation", "out_of_sample"):
            result = run_one(h1, split[label], features_by_period[label], tier)
            summarize(f"  {label}", result)
            cost_sensitivity[tier][label] = result.summary

    # --- 2. Parameter neighborhood (one at a time), BASE cost only ---
    print("\n=== PARAMETER NEIGHBORHOOD (BASE cost, one param at a time) ===")
    neighborhood_results = {}
    for d in DISTANCE_NEIGHBORHOOD:
        variant = build_variant(d, 0.0015, f"distance_{d}")
        neighborhood_results[f"distance_{d}"] = {}
        print(f" distance={d} (atr_ceiling fixed at 0.0015):")
        for label in ("development", "validation", "out_of_sample"):
            result = run_one(variant, split[label], features_by_period[label], "BASE")
            summarize(f"  {label}", result)
            neighborhood_results[f"distance_{d}"][label] = result.summary
    for a in ATR_CEILING_NEIGHBORHOOD:
        variant = build_variant(0.0005, a, f"atr_{a}")
        neighborhood_results[f"atr_ceiling_{a}"] = {}
        print(f" atr_ceiling={a} (distance fixed at 0.0005):")
        for label in ("development", "validation", "out_of_sample"):
            result = run_one(variant, split[label], features_by_period[label], "BASE")
            summarize(f"  {label}", result)
            neighborhood_results[f"atr_ceiling_{a}"][label] = result.summary

    # --- 3. Statistical analysis on H1's actual out-of-sample trades (BASE cost) ---
    print("\n=== STATISTICAL ANALYSIS (H1, out-of-sample, BASE cost) ===")
    oos_result = run_one(h1, split["out_of_sample"], features_by_period["out_of_sample"], "BASE")
    oos_trades = oos_result.trades

    payoff = compute_payoff_stats(oos_trades)
    breakeven = compute_breakeven_win_rate(payoff.payoff_ratio)
    wins = sum(1 for t in oos_trades if t.net_pnl > 0)
    wilson = wilson_confidence_interval(wins, len(oos_trades))
    bootstrap_ci = bootstrap_pnl_confidence_interval([t.net_pnl for t in oos_trades])

    print(f"  trades={len(oos_trades)} wins={wins} actual_win_rate={wins/len(oos_trades):.4f}")
    print(f"  average_win={payoff.average_win:.2f} average_loss={payoff.average_loss:.2f}")
    print(f"  largest_win={payoff.largest_win:.2f} largest_loss={payoff.largest_loss:.2f}")
    print(f"  payoff_ratio={payoff.payoff_ratio:.4f}")
    print(f"  breakeven_win_rate={breakeven:.4f}")
    print(f"  wilson_95_ci={wilson}")
    print(f"  bootstrap_95_ci_total_pnl={bootstrap_ci}")

    # --- 4. Regime dependence (H1 out-of-sample trades) ---
    print("\n=== REGIME DEPENDENCE (H1, out-of-sample) ===")
    contexts = attach_context_to_trades(oos_trades, features_by_period["out_of_sample"])
    by_regime = group_by_regime(contexts)
    for regime_label, stats in sorted(by_regime.items(), key=lambda kv: -kv[1].trade_count):
        wr = f"{stats.win_rate:.3f}" if stats.win_rate is not None else "n/a"
        print(f"  {regime_label:18s}: n={stats.trade_count:4d} win_rate={wr} net_pnl={stats.net_pnl:.2f}")

    return {
        "cost_sensitivity": cost_sensitivity,
        "neighborhood_results": neighborhood_results,
        "oos_trades": oos_trades,
        "payoff": payoff,
        "breakeven": breakeven,
        "wilson": wilson,
        "bootstrap_ci": bootstrap_ci,
        "by_regime": by_regime,
    }


if __name__ == "__main__":
    main()
