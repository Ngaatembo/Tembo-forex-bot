"""
Phase 12 — regime-conditional analysis of already-tested strategies.

Breakout and crossover are NOT re-run here: breakout's regime-filtered
performance was already fully answered in Phase 9.1 (12 combinations,
all REJECTED, family SATURATED); crossover's regime breakdown was
already computed in Phase 5. Re-running either would duplicate
completed work. New compute here covers H1 and the four momentum
hypotheses (T1@60, T2, T3), which have never been regime-filtered.

Filters (pre-registered, fixed before any result seen):
  5 single-regime: TRENDING_UP, TRENDING_DOWN, RANGING, HIGH_VOLATILITY, LOW_VOLATILITY
  1 combined: TRENDING_UP|TRENDING_DOWN|HIGH_VOLATILITY — reused from
  Phase 9.1's own most-evidence-motivated combination for breakout,
  applied here for methodological consistency, not new reasoning.

PREDICTED BEFORE RUNNING: H1's own entry requires atr_percent < 0.0015,
which structurally excludes HIGH_VOLATILITY (atr_percent > 0.0015) —
that filter should yield near-zero H1 trades by construction.
"""

import sys

from app.backtesting.config import BacktestConfig
from app.backtesting.engine_research import simulate_trades_with_exit_rules
from app.backtesting.exit_rules import ExitConfig
from app.data_engine.importers.ejtrader_source import import_ejtrader_eurusd_h1
from app.data_engine.normalizer import normalize_candles
from app.research.periods import EvaluationPeriod, EvaluationPeriods, split_candles_by_period
from app.research.verdict import compute_verdict
from app.strategy_engine.momentum import (
    detect_confirmed_trend_signals, detect_momentum_signals, detect_vol_normalized_signals,
)
from app.strategy_engine.regime_filter import filter_signals_by_regime
from app.technical_engine.features import calculate_feature_snapshots

sys.path.insert(0, "scripts")

COST_TIERS = {
    "LOW": {"spread": 0.00005, "slippage": 0.00001},
    "BASE": {"spread": 0.00010, "slippage": 0.00002},
    "HIGH": {"spread": 0.00020, "slippage": 0.00005},
}
ACCOUNT = {"initial_balance": 10000.0, "position_size": 10000.0}

REGIME_FILTERS = {
    "TRENDING_UP": {"TRENDING_UP"},
    "TRENDING_DOWN": {"TRENDING_DOWN"},
    "RANGING": {"RANGING"},
    "HIGH_VOLATILITY": {"HIGH_VOLATILITY"},
    "LOW_VOLATILITY": {"LOW_VOLATILITY"},
    "TRENDING_OR_HIGH_VOL": {"TRENDING_UP", "TRENDING_DOWN", "HIGH_VOLATILITY"},
}


def h1_base_signals(candles, features):
    from app.research.rule_signal_generator import generate_signals_from_hypothesis
    from run_phase8_hypotheses import build_h1_range_extreme_reversion
    hypothesis = build_h1_range_extreme_reversion()
    return generate_signals_from_hypothesis(hypothesis, candles, features)


def momentum_base_signals(name, candles, features):
    if name == "T1_lookback60":
        return detect_momentum_signals(candles, lookback=60, symbol="EUR/USD")
    if name == "T2_volnorm60":
        return detect_vol_normalized_signals(candles, features, lookback=60, threshold=6.0, symbol="EUR/USD")
    if name == "T3_confirmed60":
        return detect_confirmed_trend_signals(candles, primary_lookback=60, secondary_lookback=15, symbol="EUR/USD")
    raise ValueError(name)


STRATEGIES = ["H1", "T1_lookback60", "T2_volnorm60", "T3_confirmed60"]


def base_signals(name, candles, features):
    if name == "H1":
        return h1_base_signals(candles, features)
    return momentum_base_signals(name, candles, features)


def exit_config_for(name):
    if name == "H1":
        return ExitConfig(label="baseline")
    return ExitConfig(label="momentum_exit", atr_stop_multiple=2.0, max_holding_candles=120)


def run_one(name, signals, candles, features, cost_key):
    config = BacktestConfig(**ACCOUNT, **COST_TIERS[cost_key])
    return simulate_trades_with_exit_rules(candles, signals, features, config, exit_config_for(name))


def main():
    csv_path = "/home/claude/real_data/EURUSDh1.csv"
    candles = normalize_candles(import_ejtrader_eurusd_h1(csv_path))
    n = len(candles)
    train_end, val_end = int(n * 0.70), int(n * 0.85)
    periods = EvaluationPeriods(
        development=EvaluationPeriod("development", candles[0].timestamp, candles[train_end].timestamp),
        validation=EvaluationPeriod("validation", candles[train_end].timestamp, candles[val_end].timestamp),
        out_of_sample=EvaluationPeriod("out_of_sample", candles[val_end].timestamp, candles[-1].timestamp),
    )
    split = split_candles_by_period(candles, periods)
    features_by_period = {label: calculate_feature_snapshots(c) for label, c in split.items()}

    results = {}
    for strat_name in STRATEGIES:
        results[strat_name] = {}
        base_signals_by_period = {
            label: base_signals(strat_name, split[label], features_by_period[label])
            for label in ("development", "validation", "out_of_sample")
        }

        results[strat_name]["UNFILTERED"] = {}
        for tier in COST_TIERS:
            results[strat_name]["UNFILTERED"][tier] = {}
            for label in ("development", "validation", "out_of_sample"):
                r = run_one(strat_name, base_signals_by_period[label], split[label], features_by_period[label], tier)
                results[strat_name]["UNFILTERED"][tier][label] = r
        base_periods = {l: results[strat_name]["UNFILTERED"]["BASE"][l].summary for l in ("development", "validation", "out_of_sample")}
        unfiltered_verdict = compute_verdict(**base_periods)
        print(f"\n=== {strat_name} — UNFILTERED === verdict={unfiltered_verdict.value}")
        for label in ("development", "validation", "out_of_sample"):
            s = base_periods[label]
            pf = f"{s.profit_factor:.3f}" if s.profit_factor else "n/a"
            print(f"  {label}: trades={s.trade_count} pf={pf}")

        for filter_name, allowed in REGIME_FILTERS.items():
            results[strat_name][filter_name] = {}
            filtered_by_period = {
                label: filter_signals_by_regime(base_signals_by_period[label], features_by_period[label], allowed)
                for label in ("development", "validation", "out_of_sample")
            }
            for tier in COST_TIERS:
                results[strat_name][filter_name][tier] = {}
                for label in ("development", "validation", "out_of_sample"):
                    r = run_one(strat_name, filtered_by_period[label], split[label], features_by_period[label], tier)
                    results[strat_name][filter_name][tier][label] = r

            f_base = {l: results[strat_name][filter_name]["BASE"][l].summary for l in ("development", "validation", "out_of_sample")}
            verdict = compute_verdict(**f_base)
            retention = f_base["out_of_sample"].trade_count / base_periods["out_of_sample"].trade_count * 100 if base_periods["out_of_sample"].trade_count else 0
            pf = f"{f_base['out_of_sample'].profit_factor:.3f}" if f_base["out_of_sample"].profit_factor else "n/a"
            print(f"  [{filter_name}] oos_trades={f_base['out_of_sample'].trade_count} (retention {retention:.1f}%) oos_pf={pf} verdict={verdict.value}")
            results[strat_name][filter_name]["verdict_base_cost"] = verdict

    return results, split, features_by_period


if __name__ == "__main__":
    main()
