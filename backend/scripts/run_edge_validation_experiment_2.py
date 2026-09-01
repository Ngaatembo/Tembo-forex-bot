"""
Edge Validation Experiment 2 — Full-Fidelity Real Selector Test.

For every walk-forward window, constructs GENUINE ValidatedStrategyConfig
objects (real parameter neighborhoods, real LOW/BASE/HIGH cost-tier
sweeps, real Wilson/bootstrap statistical evidence, real
verdict/overfitting/scorecard/gate computation) and passes them into
the ACTUAL, UNMODIFIED app.research.strategy_selector.select_strategy().
No simplified selector. No modification to any research module.

Every primitive reused verbatim from existing modules:
  compute_verdict, compute_overfitting_diagnostics, compute_scorecard,
  compute_research_gate, select_strategy (all app.research.*)
  wilson_confidence_interval, bootstrap_pnl_confidence_interval,
  compute_payoff_stats, compute_breakeven_win_rate (statistics_analysis.py)
  simulate_trades, simulate_trades_with_exit_rules (existing engines)

METHODOLOGICAL NOTE: this is a test of whether the selection mechanism
adds measurable OOS value, not proof of profitability.
"""

import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone

sys.path.insert(0, ".")

from app.backtesting.config import BacktestConfig
from app.backtesting.engine import simulate_trades
from app.backtesting.engine_research import simulate_trades_with_exit_rules
from app.backtesting.exit_rules import ExitConfig
from app.backtesting.metrics import compute_metrics
from app.backtesting.models import BacktestResult
from app.data_engine.importers.csv_importer import import_candles_from_csv
from app.data_engine.importers.ejtrader_source import ejtrader_import_config, ejtrader_xauusd_import_config
from app.data_engine.normalizer import normalize_candles
from app.research.hypothesis import HypothesisType
from app.research.overfitting import compute_overfitting_diagnostics
from app.research.periods import split_candles_by_period
from app.research.research_gate import compute_research_gate
from app.research.scorecard import compute_scorecard
from app.research.statistics_analysis import (
    bootstrap_pnl_confidence_interval, compute_breakeven_win_rate, compute_payoff_stats, wilson_confidence_interval,
)
from app.research.strategy_selector import select_strategy
from app.research.validated_strategy_config import ValidatedStrategyConfig
from app.research.verdict import compute_verdict
from app.research.walk_forward import WalkForwardConfig, generate_walk_forward_windows
from app.strategy_engine.breakout import detect_breakout_signals
from app.strategy_engine.crossover import detect_crossover_signals
from app.strategy_engine.momentum import detect_momentum_signals
from app.strategy_engine.regime_filter import filter_signals_by_regime
from app.technical_engine.features import calculate_feature_snapshots
from app.technical_engine.indicators import calculate_sma
from app.technical_engine.models import TechnicalFeature

DATASET_SOURCE = "https://github.com/ejtraderLabs/historical-data"
DATA_PATHS = {
    "EUR/USD": ("/home/claude/real_data/EURUSDh1.csv", ejtrader_import_config()),
    "GBP/USD": ("/home/claude/real_data/GBPUSDh1.csv", ejtrader_import_config()),
    "XAU/USD": ("/home/claude/real_data/XAUUSDh1.csv", ejtrader_xauusd_import_config()),
}
POSITION_SIZE = {"EUR/USD": 10_000.0, "GBP/USD": 10_000.0, "XAU/USD": 8.298216860650118}
INITIAL_BALANCE = 10000.0
COST_TIERS = {
    "LOW": {"spread": 0.00005, "slippage": 0.00001},
    "BASE": {"spread": 0.00010, "slippage": 0.00002},
    "HIGH": {"spread": 0.00020, "slippage": 0.00005},
}
BREAKOUT_EXIT = ExitConfig(label="atr_2x_max100", atr_stop_multiple=2.0, max_holding_candles=100)
REGIME_FILTER_SET = {"HIGH_VOLATILITY", "TRENDING_DOWN", "TRENDING_UP"}

SMA_NEIGHBORHOOD = [(5, 20), (10, 50), (20, 100)]
BREAKOUT_NEIGHBORHOOD = [20, 40, 60]
MOMENTUM_NEIGHBORHOOD = [10, 20, 30]

WF_CONFIG = WalkForwardConfig(development_days=1000, validation_days=200, out_of_sample_days=200, step_days=200)


def load_candles(instrument):
    path, config = DATA_PATHS[instrument]
    return normalize_candles(import_candles_from_csv(path, symbol=instrument, timeframe="1h", config=config))


def make_config(instrument, cost_tier):
    return BacktestConfig(
        symbol=instrument, timeframe="1h", initial_balance=INITIAL_BALANCE,
        position_size=POSITION_SIZE[instrument], **COST_TIERS[cost_tier],
    )


def _empty_result(config):
    return BacktestResult(configuration=config, summary=compute_metrics([], [], config.initial_balance), trades=[], equity_curve=[])


def build_sma_features(candles, fast, slow):
    if not candles:
        return []
    closes = [c.close for c in candles]
    fast_vals = calculate_sma(closes, period=fast)
    slow_vals = calculate_sma(closes, period=slow)
    return [
        TechnicalFeature(timestamp=c.timestamp, close=c.close, sma_10=fast_vals[i], sma_50=slow_vals[i])
        for i, c in enumerate(candles)
    ]


def run_sma(candles, instrument, cost_tier, fast, slow):
    config = make_config(instrument, cost_tier)
    if not candles:
        return _empty_result(config)
    features = build_sma_features(candles, fast, slow)
    signals = detect_crossover_signals(features, symbol=instrument)
    return simulate_trades(candles, signals, config)


def run_breakout(candles, instrument, cost_tier, lookback, regime_filtered=False):
    config = make_config(instrument, cost_tier)
    if not candles:
        return _empty_result(config)
    signals = detect_breakout_signals(candles, lookback=lookback, symbol=instrument)
    features = calculate_feature_snapshots(candles)
    if regime_filtered:
        signals = filter_signals_by_regime(signals, features, REGIME_FILTER_SET)
    return simulate_trades_with_exit_rules(candles, signals, features, config, BREAKOUT_EXIT)


def run_momentum(candles, instrument, cost_tier, lookback):
    config = make_config(instrument, cost_tier)
    if not candles:
        return _empty_result(config)
    signals = detect_momentum_signals(candles, lookback=lookback, symbol=instrument)
    features = calculate_feature_snapshots(candles)
    return simulate_trades_with_exit_rules(candles, signals, features, config, BREAKOUT_EXIT)


FAMILY_RUNNERS = {
    "sma_crossover": lambda candles, instrument, cost_tier, param: run_sma(candles, instrument, cost_tier, *param),
    "breakout": lambda candles, instrument, cost_tier, param: run_breakout(candles, instrument, cost_tier, param),
    "momentum": lambda candles, instrument, cost_tier, param: run_momentum(candles, instrument, cost_tier, param),
    "regime_filtered_breakout": lambda candles, instrument, cost_tier, param: run_breakout(candles, instrument, cost_tier, param, regime_filtered=True),
}
FAMILY_NEIGHBORHOODS = {
    "sma_crossover": SMA_NEIGHBORHOOD, "breakout": BREAKOUT_NEIGHBORHOOD,
    "momentum": MOMENTUM_NEIGHBORHOOD, "regime_filtered_breakout": BREAKOUT_NEIGHBORHOOD,
}
FAMILY_HYPOTHESIS_TYPE = {
    "sma_crossover": HypothesisType.TREND_FOLLOWING, "breakout": HypothesisType.BREAKOUT,
    "momentum": HypothesisType.MOMENTUM, "regime_filtered_breakout": HypothesisType.BREAKOUT,
}


def build_statistical_evidence(trades):
    if not trades:
        return None
    n = len(trades)
    wins = sum(1 for t in trades if t.net_pnl > 0)
    wilson = wilson_confidence_interval(wins, n)
    pnls = [t.net_pnl for t in trades]
    bootstrap = bootstrap_pnl_confidence_interval(pnls)
    payoff = compute_payoff_stats(trades)
    breakeven = compute_breakeven_win_rate(payoff.payoff_ratio)
    if wilson is None or bootstrap is None:
        return None
    return {"wilson_ci": wilson, "bootstrap_ci_total_pnl": bootstrap, "breakeven_win_rate": breakeven, "actual_win_rate": wins / n}


def evaluate_family_for_window(family, instrument, split, window_index):
    neighborhood = FAMILY_NEIGHBORHOODS[family]
    runner = FAMILY_RUNNERS[family]

    per_param_results = {}
    for param in neighborhood:
        per_param_results[param] = {
            label: runner(split[label], instrument, "BASE", param)
            for label in ("development", "validation", "out_of_sample")
        }

    def val_pf(param):
        pf = per_param_results[param]["validation"].summary.profit_factor
        trades = per_param_results[param]["validation"].summary.trade_count
        return pf if (pf is not None and trades > 0) else float("-inf")
    primary_param = max(neighborhood, key=val_pf)

    primary = per_param_results[primary_param]
    dev_summary, val_summary, oos_summary_base = (primary[l].summary for l in ("development", "validation", "out_of_sample"))

    verdict = compute_verdict(dev_summary, val_summary, oos_summary_base)
    overfitting = compute_overfitting_diagnostics(dev_summary, val_summary, oos_summary_base)

    cost_tier_summaries = {"BASE": oos_summary_base}
    for tier in ("LOW", "HIGH"):
        cost_tier_summaries[tier] = runner(split["out_of_sample"], instrument, tier, primary_param).summary

    statistical_evidence = build_statistical_evidence(primary["out_of_sample"].trades)

    parameter_neighborhood_summaries = [per_param_results[p]["out_of_sample"].summary for p in neighborhood]

    scorecard = compute_scorecard(
        period_summaries={"development": dev_summary, "validation": val_summary, "out_of_sample": oos_summary_base},
        verdict=verdict, overfitting=overfitting,
        parameter_neighborhood=parameter_neighborhood_summaries,
        cost_tier_summaries=cost_tier_summaries,
        statistical_evidence=statistical_evidence,
        regime_dependence=None,
    )
    gate = compute_research_gate(verdict, scorecard, overfitting)

    config = ValidatedStrategyConfig(
        config_id=f"{family}_{primary_param}_{instrument.replace('/', '')}_{window_index}",
        candidate_id=f"{family}_{instrument.replace('/', '')}",
        instrument=instrument, timeframe="h1", strategy_family=FAMILY_HYPOTHESIS_TYPE[family],
        parameters={"primary_param": str(primary_param), "neighborhood": str(neighborhood)},
        exit_config_summary={} if family == "sma_crossover" else {"atr_stop_multiple": 2.0, "max_holding_candles": 100},
        cost_assumptions=COST_TIERS["BASE"],
        evidence_period_start=split["development"][0].timestamp.isoformat() if split["development"] else "",
        evidence_period_end=split["out_of_sample"][-1].timestamp.isoformat() if split["out_of_sample"] else "",
        gate_status=gate.status, verdict=verdict.value, statistical_level=scorecard.statistical.level,
        regime_evidence={},
    )

    evidence = {
        "primary_param": str(primary_param), "verdict": verdict.value, "gate_status": gate.status, "gate_reason": gate.reason,
        "scorecard": {
            "edge": asdict(scorecard.edge), "robustness": asdict(scorecard.robustness), "risk": asdict(scorecard.risk),
            "statistical": asdict(scorecard.statistical), "realism": asdict(scorecard.realism),
        },
        "development": {"trades": dev_summary.trade_count, "profit_factor": dev_summary.profit_factor},
        "validation": {"trades": val_summary.trade_count, "profit_factor": val_summary.profit_factor},
        "out_of_sample_base": {"trades": oos_summary_base.trade_count, "profit_factor": oos_summary_base.profit_factor},
        "neighborhood_oos_pfs": {str(p): s.profit_factor for p, s in zip(neighborhood, parameter_neighborhood_summaries)},
        "cost_tier_oos_pfs": {t: s.profit_factor for t, s in cost_tier_summaries.items()},
    }

    return config, primary["out_of_sample"], evidence


def main():
    full_report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "methodology_note": (
            "Tests whether Tembo's REAL, UNMODIFIED research gate + strategy selector adds "
            "measurable out-of-sample value under rolling walk-forward validation. Historical "
            "OOS results do not guarantee future profitability."
        ),
        "dataset_source": DATASET_SOURCE,
        "walk_forward_config": {"development_days": 1000, "validation_days": 200, "out_of_sample_days": 200, "step_days": 200},
        "neighborhoods": {"sma_crossover": SMA_NEIGHBORHOOD, "breakout": BREAKOUT_NEIGHBORHOOD, "momentum": MOMENTUM_NEIGHBORHOOD, "regime_filtered_breakout": BREAKOUT_NEIGHBORHOOD},
        "results": {},
    }

    for instrument in ("EUR/USD", "GBP/USD", "XAU/USD"):
        print(f"=== {instrument} ===")
        candles = load_candles(instrument)
        windows = generate_walk_forward_windows(candles, WF_CONFIG)
        print(f"  {len(windows)} windows")

        selector_windows = []
        baseline_oos = {f: [] for f in FAMILY_RUNNERS}

        for window in windows:
            split = split_candles_by_period(candles, window.periods)
            print(f"  window {window.index}: evaluating 4 families x neighborhoods...")

            configs_this_window = []
            oos_results_by_config_id = {}
            evidence_by_family = {}
            for family in FAMILY_RUNNERS:
                config, oos_result, evidence = evaluate_family_for_window(family, instrument, split, window.index)
                configs_this_window.append(config)
                oos_results_by_config_id[config.config_id] = oos_result
                evidence_by_family[family] = evidence
                baseline_oos[family].append({"window_index": window.index, "summary": asdict(oos_result.summary)})

            selection = select_strategy(instrument, "h1", configs_this_window)
            selected_oos = oos_results_by_config_id.get(selection.selected_config_id) if selection.selected_config_id else None

            selector_windows.append({
                "window_index": window.index,
                "development": window.periods.development.to_dict(), "validation": window.periods.validation.to_dict(),
                "out_of_sample": window.periods.out_of_sample.to_dict(),
                "candidates_evidence": evidence_by_family,
                "selector_status": selection.status, "selected_config_id": selection.selected_config_id,
                "selector_reason": selection.reason,
                "selected_oos_summary": asdict(selected_oos.summary) if selected_oos else None,
            })
            print(f"    -> selector status={selection.status}, selected={selection.selected_config_id}")

        full_report["results"][instrument] = {"selector_windows": selector_windows, "fixed_baselines": baseline_oos}

        out_path = "/home/claude/ai-trading-platform/research/results/edge_validation_experiment_2.json"
        with open(out_path, "w") as f:
            json.dump(full_report, f, indent=2, default=str)
        print(f"  (partial) saved to {out_path}")

    print(f"\nDone. Saved to {out_path}")
    return full_report


if __name__ == "__main__":
    main()
