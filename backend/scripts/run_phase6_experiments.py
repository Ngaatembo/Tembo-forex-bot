"""
Phase 6 pre-registered experiment run.

PRE-REGISTRATION: every hypothesis, parameter, and period boundary
below was fixed BEFORE this script was ever run against the
validation or out-of-sample periods. The dev/train period is the only
place any of these numbers could have been (and were NOT) tuned
against. Do not add new experiments to this file after seeing
validation/out-of-sample results without noting that explicitly as a
NEW, separately-labeled hypothesis — never silently retro-fit.

Six configurations tested, each isolating exactly one variable against
the frozen baseline:

  baseline            — unchanged Phase 3 strategy, opposite-crossover exit only
  entry_low_vol       — baseline entries filtered to exclude LOW_VOLATILITY-regime signals
  entry_extreme_rsi   — baseline entries filtered to exclude overbought BUY / oversold SELL
  exit_fixed_stop_1pct— baseline entries, +1% fixed stop-loss (OR opposite crossover, whichever first)
  exit_atr_stop_2x    — baseline entries, stop = entry -/+ 2x ATR14-at-entry
  exit_max_hold_200   — baseline entries, forced exit after 200 candles (~8.3 days) if still open

Each runs across three chronological periods (same 70/15/15 split as
Phase 4.5) at BASE_COST, plus the full period at ZERO_COST as a
diagnostic only (never the headline number).
"""

import argparse
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from app.backtesting.config import BacktestConfig
from app.backtesting.engine import run_backtest as run_baseline_backtest
from app.backtesting.engine_research import simulate_trades_with_exit_rules
from app.backtesting.exit_rules import BASELINE_EXIT, ExitConfig
from app.data_engine.importers.ejtrader_source import import_ejtrader_eurusd_h1
from app.data_engine.normalizer import normalize_candles
from app.research.experiment import (
    BASELINE_STRATEGY_VERSION, build_experiment_record, make_experiment_id, save_experiment,
)
from app.strategy_engine.entry_filters import filter_avoid_extreme_rsi, filter_avoid_low_volatility
from app.strategy_engine.service import run_crossover_strategy
from app.technical_engine.features import calculate_feature_snapshots

BASE_COST = dict(spread=0.00010, slippage=0.00002)
ZERO_COST = dict(spread=0.0, slippage=0.0)
ACCOUNT = dict(initial_balance=10000.0, position_size=10000.0)
DATASET_ID = "ejtraderLabs_historical-data_EURUSD_h1"

EXIT_CONFIGS = {
    "baseline": BASELINE_EXIT,
    "exit_fixed_stop_1pct": ExitConfig(label="exit_fixed_stop_1pct", stop_loss_pct=0.01),
    "exit_atr_stop_2x": ExitConfig(label="exit_atr_stop_2x", atr_stop_multiple=2.0),
    "exit_max_hold_200": ExitConfig(label="exit_max_hold_200", max_holding_candles=200),
}


def serialize(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Not JSON serializable: {type(obj)}")


def run_one(candles, features, entry_label, exit_label, cost_params) -> dict:
    signals = run_crossover_strategy(candles, symbol="EUR/USD")

    if entry_label == "entry_low_vol":
        signals = filter_avoid_low_volatility(signals, features)
    elif entry_label == "entry_extreme_rsi":
        signals = filter_avoid_extreme_rsi(signals, features)
    # entry_label == "baseline" -> signals unchanged

    exit_config = EXIT_CONFIGS[exit_label]
    config = BacktestConfig(**ACCOUNT, **cost_params)

    if entry_label == "baseline" and exit_label == "baseline":
        # Pure baseline row only: route through Phase 4's own frozen
        # function as an independent cross-check (proven identical to
        # the research engine at BASELINE_EXIT by
        # test_baseline_exit_config_matches_phase4_baseline_engine_exactly).
        result = run_baseline_backtest(candles, config)
    else:
        # Any entry filter or exit rule MUST go through the research
        # engine with the (possibly filtered) `signals` computed above —
        # calling run_baseline_backtest here would silently recompute
        # fresh unfiltered signals internally and discard the filter
        # entirely. (This was a real bug, caught by identical results
        # across entry_low_vol/entry_extreme_rsi/baseline — fixed here.)
        result = simulate_trades_with_exit_rules(candles, signals, features, config, exit_config)

    return {"result": result, "config": config}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True)
    parser.add_argument("--output-dir", default="../research/results")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    registry_path = output_dir / "phase_6_experiments.json"

    print(f"Importing {args.csv} ...")
    candles = normalize_candles(import_ejtrader_eurusd_h1(args.csv))
    print(f"{len(candles)} candles, {candles[0].timestamp} -> {candles[-1].timestamp}")

    print("Computing Phase 5 feature snapshots (needed by entry filters)...")
    features = calculate_feature_snapshots(candles)

    n = len(candles)
    train_end, val_end = int(n * 0.70), int(n * 0.85)
    periods = {
        "train_dev": (candles[:train_end], features[:train_end]),
        "validation": (candles[train_end:val_end], features[train_end:val_end]),
        "out_of_sample": (candles[val_end:], features[val_end:]),
    }

    configurations = [
        ("baseline", "baseline"),
        ("entry_low_vol", "baseline"),
        ("entry_extreme_rsi", "baseline"),
        ("baseline", "exit_fixed_stop_1pct"),
        ("baseline", "exit_atr_stop_2x"),
        ("baseline", "exit_max_hold_200"),
    ]

    all_results = {}

    for entry_label, exit_label in configurations:
        config_key = f"{entry_label}__{exit_label}"
        all_results[config_key] = {}
        for period_label, (period_candles, period_features) in periods.items():
            run = run_one(period_candles, period_features, entry_label, exit_label, BASE_COST)
            summary = run["result"].summary

            record = build_experiment_record(
                experiment_id=make_experiment_id(config_key), strategy_version=BASELINE_STRATEGY_VERSION,
                entry_rule_label=entry_label, exit_rule_label=exit_label,
                risk_config_label="fixed_10000_notional", dataset_id=DATASET_ID,
                period_label=period_label,
                period_start=period_candles[0].timestamp, period_end=period_candles[-1].timestamp,
                candle_count=len(period_candles), spread=BASE_COST["spread"], slippage=BASE_COST["slippage"],
                initial_balance=ACCOUNT["initial_balance"], position_size=ACCOUNT["position_size"],
                summary=summary,
            )
            save_experiment(record, registry_path)

            all_results[config_key][period_label] = asdict(summary)
            pf = f"{summary.profit_factor:.3f}" if summary.profit_factor is not None else "n/a"
            print(
                f"  [{config_key}] {period_label}: trades={summary.trade_count} "
                f"return={summary.total_return:.4f} profit_factor={pf}"
            )

    # zero-cost diagnostic, full period, baseline only
    zc_run = run_one(candles, features, "baseline", "baseline", ZERO_COST)
    zc_summary = zc_run["result"].summary
    print(
        f"\n[ZERO_COST_DIAGNOSTIC full period, baseline]: trades={zc_summary.trade_count} "
        f"return={zc_summary.total_return:.4f}"
    )

    output = {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "dataset_id": DATASET_ID,
            "candle_count": len(candles),
            "period_start": candles[0].timestamp.isoformat(),
            "period_end": candles[-1].timestamp.isoformat(),
            "cost_assumptions_base": BASE_COST,
            "account": ACCOUNT,
            "note": "All non-baseline results are BASE_COST unless labeled zero-cost-diagnostic.",
        },
        "results_by_configuration_and_period": all_results,
        "zero_cost_diagnostic_full_period_baseline": asdict(zc_summary),
    }

    summary_file = output_dir / "phase_6_summary.json"
    summary_file.write_text(json.dumps(output, indent=2, default=serialize))
    print(f"\nSaved summary to {summary_file}")
    print(f"Saved full experiment registry to {registry_path}")


if __name__ == "__main__":
    main()
