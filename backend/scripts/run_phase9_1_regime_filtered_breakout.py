"""
Phase 9.1 — regime-filtered breakout validation.

Reuses Phase 9's exact breakout signal generation, exit config,
lookback neighborhood, cost tiers, and account config via direct
import (never retyped) — this experiment can ONLY change whether a
signal is accepted or suppressed by regime, nothing about the
underlying strategy.

Three PRE-REGISTERED regime filters (fixed before this script ran
against any result):
  A: {TRENDING_UP, TRENDING_DOWN}
  B: {HIGH_VOLATILITY}
  C: {TRENDING_UP, TRENDING_DOWN, HIGH_VOLATILITY}
No filter is added, removed, or adjusted after seeing results.
"""

import sys
sys.path.insert(0, "scripts")

from run_phase9_breakout import ACCOUNT, ATR_STOP_MULTIPLE, COST_TIERS, LOOKBACK_NEIGHBORHOOD, MAX_HOLDING_CANDLES

from app.backtesting.config import BacktestConfig
from app.backtesting.engine_research import simulate_trades_with_exit_rules
from app.backtesting.exit_rules import ExitConfig
from app.data_engine.importers.ejtrader_source import import_ejtrader_eurusd_h1
from app.data_engine.normalizer import normalize_candles
from app.research.periods import EvaluationPeriod, EvaluationPeriods, split_candles_by_period
from app.research.verdict import compute_verdict
from app.strategy_engine.breakout import detect_breakout_signals
from app.strategy_engine.regime_filter import filter_signals_by_regime
from app.technical_engine.features import calculate_feature_snapshots

REGIME_FILTERS = {
    "A_trending_only": {"TRENDING_UP", "TRENDING_DOWN"},
    "B_high_vol_only": {"HIGH_VOLATILITY"},
    "C_trending_or_high_vol": {"TRENDING_UP", "TRENDING_DOWN", "HIGH_VOLATILITY"},
}


def run_one(candles, features, lookback, cost_key, filter_regimes):
    raw_signals = detect_breakout_signals(candles, lookback=lookback, symbol="EUR/USD")
    signals = (
        filter_signals_by_regime(raw_signals, features, filter_regimes)
        if filter_regimes is not None else raw_signals
    )
    exit_config = ExitConfig(
        label="breakout_atr_stop_and_max_hold",
        atr_stop_multiple=ATR_STOP_MULTIPLE, max_holding_candles=MAX_HOLDING_CANDLES,
    )
    config = BacktestConfig(**ACCOUNT, **COST_TIERS[cost_key])
    result = simulate_trades_with_exit_rules(candles, signals, features, config, exit_config)
    original_signal_count = sum(1 for s in raw_signals if s.direction in ("BUY", "SELL"))
    return result, original_signal_count


def summarize(label, result, original_count):
    s = result.summary
    pf = f"{s.profit_factor:.3f}" if s.profit_factor is not None else "n/a"
    retention = f"{s.trade_count/original_count*100:.1f}%" if original_count else "n/a"
    print(f"  {label:24s}: trades={s.trade_count:5d} (retained {retention} of {original_count})  return={s.total_return:8.4f}  pf={pf}")


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

    all_results = {}

    for lookback in LOOKBACK_NEIGHBORHOOD:
        all_results[lookback] = {}
        print(f"\n########## lookback={lookback} ##########")

        for filter_name, filter_regimes in [("UNFILTERED", None)] + list(REGIME_FILTERS.items()):
            print(f"\n=== {filter_name} ===")
            all_results[lookback][filter_name] = {}
            base_period_summaries = {}

            for tier in COST_TIERS:
                all_results[lookback][filter_name][tier] = {}
                print(f" {tier}:")
                for label in ("development", "validation", "out_of_sample"):
                    result, orig_count = run_one(split[label], features_by_period[label], lookback, tier, filter_regimes)
                    summarize(f"  {label}", result, orig_count)
                    all_results[lookback][filter_name][tier][label] = {
                        "summary": result.summary, "original_signal_count": orig_count,
                    }
                    if tier == "BASE":
                        base_period_summaries[label] = result.summary

            verdict = compute_verdict(
                base_period_summaries["development"], base_period_summaries["validation"],
                base_period_summaries["out_of_sample"],
            )
            print(f" VERDICT (BASE cost): {verdict.value}")
            all_results[lookback][filter_name]["verdict_base_cost"] = verdict.value

    return all_results


if __name__ == "__main__":
    main()
