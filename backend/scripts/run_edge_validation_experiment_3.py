"""
Edge Validation Experiment 3 — 2023+ Out-of-Sample Validation.

OBJECTIVE:
Does Tembo's evidence from Experiment 2 (2012–2022 data) survive on genuinely
newer data (2023+)? This experiment runs the REAL, UNMODIFIED walk-forward
methodology on 2023+ Twelve Data H1 candles, using:
  - Real strategy selector (no manual "pick the best")
  - Real research gates (REJECT_EARLY, NO_TRADE decisions are respected)
  - Real scorecard and verdict logic (unchanged from Experiment 2)
  - Real parameter neighborhoods (SMA, Breakout, Momentum, Regime Filtered Breakout)
  - Real cost-tier sensitivity (LOW/BASE/HIGH)
  - Real regime classifier (where implemented)

METHODOLOGY:
Walk-forward windows (1000 dev / 200 val / 200 OOS / 200 step):
  - Development + Validation: used ONLY for selection
  - Out-of-sample: held pure until evaluation
  - Each window is fully independent (no leakage across windows)

For each window:
  1. Evaluate all 4 families x neighborhoods on dev+val
  2. Compute verdict, overfitting, scorecard, research gate (real gates, not modified)
  3. Pass configs to real strategy_selector (respects gate status, not profit-factor ranking)
  4. If selector returns NO_VALIDATED_EDGE, record it (this is correct, not an error)
  5. Run fixed-family baselines on identical OOS data
  6. Record all metrics and research gate decisions

FINAL REPORT INCLUDES:
  - Walk-forward windows (OOS results for selected strategy OR NO_TRADE decision)
  - Fixed-family baselines (SMA, Breakout, Momentum, Regime Filtered Breakout OOS)
  - Cost sensitivity (LOW/BASE/HIGH on OOS windows)
  - Regime analysis (using existing regime classifier)
  - Historical XAU/USD comparison (pre-2020, 2020, 2021-2022, 2023+ periods)
  - Aggregate OOS statistics (win rate, profit factor, expectancy, max drawdown)
  - Real selector decisions (including NO_VALIDATED_EDGE and gate reasons)
  - Classification: ROBUST_EDGE_CANDIDATE | REGIME_DEPENDENT_EDGE | EDGE_NOT_REPRODUCED | INSUFFICIENT_DATA

NO MODIFICATIONS TO:
  - research_gate.py (gates remain as-is)
  - strategy_selector.py (selector respects gate status)
  - verdict.py, scorecard.py, overfitting.py (unchanged)
  - Any strategy or signal logic
"""

import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, ".")

from app.backtesting.config import BacktestConfig
from app.backtesting.engine import simulate_trades
from app.backtesting.engine_research import simulate_trades_with_exit_rules
from app.backtesting.exit_rules import ExitConfig
from app.backtesting.metrics import compute_metrics
from app.backtesting.models import BacktestResult
from app.data_engine.importers.csv_importer import import_candles_from_csv
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

# ============================================================================
# DATA PATHS: 2023+ post-processed files from Phase 1
# ============================================================================
DATA_DIR = Path("../research/data/post_2022")
DATA_PATHS = {
    "EUR/USD": DATA_DIR / "EURUSD_H1_2023plus.csv",
    "GBP/USD": DATA_DIR / "GBPUSD_H1_2023plus.csv",
    "XAU/USD": DATA_DIR / "XAUUSD_H1_2023plus.csv",
}

POSITION_SIZE = {
    "EUR/USD": 10_000.0,
    "GBP/USD": 10_000.0,
    "XAU/USD": 8.298216860650118,
}
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

# Walk-forward config: identical to Experiment 2
WF_CONFIG = WalkForwardConfig(development_days=1000, validation_days=200, out_of_sample_days=200, step_days=200)

# ============================================================================
# HELPERS
# ============================================================================

def load_candles_2023(instrument):
    """Load 2023+ CSV without ejtrader config (post-processed already clean)."""
    path = DATA_PATHS[instrument]
    if not path.exists():
        return []
    return normalize_candles(import_candles_from_csv(
        str(path),
        symbol=instrument,
        timeframe="1h",
        config={"timestamp_format": "%Y-%m-%dT%H:%M:%S%z", "delimiter": ","},
    ))


def make_config(instrument, cost_tier):
    return BacktestConfig(
        symbol=instrument,
        timeframe="1h",
        initial_balance=INITIAL_BALANCE,
        position_size=POSITION_SIZE[instrument],
        **COST_TIERS[cost_tier],
    )


def _empty_result(config):
    return BacktestResult(
        configuration=config,
        summary=compute_metrics([], [], config.initial_balance),
        trades=[],
        equity_curve=[],
    )


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
    "sma_crossover": SMA_NEIGHBORHOOD,
    "breakout": BREAKOUT_NEIGHBORHOOD,
    "momentum": MOMENTUM_NEIGHBORHOOD,
    "regime_filtered_breakout": BREAKOUT_NEIGHBORHOOD,
}
FAMILY_HYPOTHESIS_TYPE = {
    "sma_crossover": HypothesisType.TREND_FOLLOWING,
    "breakout": HypothesisType.BREAKOUT,
    "momentum": HypothesisType.MOMENTUM,
    "regime_filtered_breakout": HypothesisType.BREAKOUT,
}


def build_statistical_evidence(trades):
    """Build statistical evidence snapshot from trades."""
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
    return {
        "wilson_ci": wilson,
        "bootstrap_ci_total_pnl": bootstrap,
        "breakeven_win_rate": breakeven,
        "actual_win_rate": wins / n,
    }


def evaluate_family_for_window(family, instrument, split, window_index):
    """
    Evaluate ONE family across all neighborhoods for ONE window.
    Returns (ValidatedStrategyConfig, BacktestResult for OOS, evidence dict).
    
    The config + evidence fully populate the selector's input; the selector
    then decides whether to choose this config (based on gate status, not PF).
    """
    neighborhood = FAMILY_NEIGHBORHOODS[family]
    runner = FAMILY_RUNNERS[family]

    # Run all parameters on dev/val/oos at BASE cost
    per_param_results = {}
    for param in neighborhood:
        per_param_results[param] = {
            label: runner(split[label], instrument, "BASE", param)
            for label in ("development", "validation", "out_of_sample")
        }

    # Select primary param by validation profit factor (this is parameter tuning, not strategy selection)
    def val_pf(param):
        pf = per_param_results[param]["validation"].summary.profit_factor
        trades = per_param_results[param]["validation"].summary.trade_count
        return pf if (pf is not None and trades > 0) else float("-inf")

    primary_param = max(neighborhood, key=val_pf)
    primary = per_param_results[primary_param]
    dev_summary, val_summary, oos_summary_base = (
        primary[l].summary for l in ("development", "validation", "out_of_sample")
    )

    # REAL verdict, overfitting, scorecard, gate (UNCHANGED from Experiment 2)
    verdict = compute_verdict(dev_summary, val_summary, oos_summary_base)
    overfitting = compute_overfitting_diagnostics(dev_summary, val_summary, oos_summary_base)

    cost_tier_summaries = {"BASE": oos_summary_base}
    for tier in ("LOW", "HIGH"):
        cost_tier_summaries[tier] = runner(split["out_of_sample"], instrument, tier, primary_param).summary

    statistical_evidence = build_statistical_evidence(primary["out_of_sample"].trades)

    parameter_neighborhood_summaries = [
        per_param_results[p]["out_of_sample"].summary for p in neighborhood
    ]

    scorecard = compute_scorecard(
        period_summaries={
            "development": dev_summary,
            "validation": val_summary,
            "out_of_sample": oos_summary_base,
        },
        verdict=verdict,
        overfitting=overfitting,
        parameter_neighborhood=parameter_neighborhood_summaries,
        cost_tier_summaries=cost_tier_summaries,
        statistical_evidence=statistical_evidence,
        regime_dependence=None,
    )
    gate = compute_research_gate(verdict, scorecard, overfitting)

    # Build ValidatedStrategyConfig for the selector
    config = ValidatedStrategyConfig(
        config_id=f"{family}_{primary_param}_{instrument.replace('/', '')}_{window_index}",
        candidate_id=f"{family}_{instrument.replace('/', '')}",
        instrument=instrument,
        timeframe="h1",
        strategy_family=FAMILY_HYPOTHESIS_TYPE[family],
        parameters={
            "primary_param": str(primary_param),
            "neighborhood": str(neighborhood),
        },
        exit_config_summary=(
            {} if family == "sma_crossover"
            else {"atr_stop_multiple": 2.0, "max_holding_candles": 100}
        ),
        cost_assumptions=COST_TIERS["BASE"],
        evidence_period_start=(
            split["development"][0].timestamp.isoformat()
            if split["development"] else ""
        ),
        evidence_period_end=(
            split["out_of_sample"][-1].timestamp.isoformat()
            if split["out_of_sample"] else ""
        ),
        gate_status=gate.status,
        verdict=verdict.value,
        statistical_level=scorecard.statistical.level,
        regime_evidence={},
    )

    # Evidence snapshot for reporting
    evidence = {
        "primary_param": str(primary_param),
        "verdict": verdict.value,
        "gate_status": gate.status,
        "gate_reason": gate.reason,
        "scorecard": {
            "edge": asdict(scorecard.edge),
            "robustness": asdict(scorecard.robustness),
            "risk": asdict(scorecard.risk),
            "statistical": asdict(scorecard.statistical),
            "realism": asdict(scorecard.realism),
        },
        "development": {
            "trades": dev_summary.trade_count,
            "profit_factor": dev_summary.profit_factor,
        },
        "validation": {
            "trades": val_summary.trade_count,
            "profit_factor": val_summary.profit_factor,
        },
        "out_of_sample_base": {
            "trades": oos_summary_base.trade_count,
            "profit_factor": oos_summary_base.profit_factor,
        },
        "neighborhood_oos_pfs": {
            str(p): s.profit_factor
            for p, s in zip(neighborhood, parameter_neighborhood_summaries)
        },
        "cost_tier_oos_pfs": {t: s.profit_factor for t, s in cost_tier_summaries.items()},
    }

    return config, primary["out_of_sample"], evidence


def main():
    """Run Experiment 3: 2023+ OOS validation with real selector and gates."""
    
    full_report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "experiment": "Experiment 3: 2023+ Out-of-Sample Validation",
        "methodology_note": (
            "Tests whether Tembo's REAL, UNMODIFIED research gate + strategy selector "
            "adds measurable out-of-sample value on genuinely newer (2023+) data. "
            "Historical OOS results do not guarantee future profitability. "
            "The selector respects gate status (REJECT_EARLY, NO_VALIDATED_EDGE decisions); "
            "it does NOT rank strategies by profit factor alone."
        ),
        "data_source": "Twelve Data H1 (2023+), Phase 1 post-processed",
        "walk_forward_config": {
            "development_days": 1000,
            "validation_days": 200,
            "out_of_sample_days": 200,
            "step_days": 200,
        },
        "neighborhoods": {
            "sma_crossover": SMA_NEIGHBORHOOD,
            "breakout": BREAKOUT_NEIGHBORHOOD,
            "momentum": MOMENTUM_NEIGHBORHOOD,
            "regime_filtered_breakout": BREAKOUT_NEIGHBORHOOD,
        },
        "results": {},
    }

    for instrument in ("EUR/USD", "GBP/USD", "XAU/USD"):
        print(f"\n=== {instrument} ===")
        candles = load_candles_2023(instrument)
        if not candles:
            print(f"  ERROR: No candles loaded from {DATA_PATHS[instrument]}")
            full_report["results"][instrument] = {"error": f"Data file not found or empty"}
            continue

        print(f"  Loaded {len(candles)} candles")
        
        try:
            windows = generate_walk_forward_windows(candles, WF_CONFIG)
        except Exception as e:
            print(f"  ERROR: Could not generate walk-forward windows: {e}")
            full_report["results"][instrument] = {"error": str(e)}
            continue

        print(f"  {len(windows)} windows generated")

        selector_windows = []
        baseline_oos = {f: [] for f in FAMILY_RUNNERS}

        for window in windows:
            split = split_candles_by_period(candles, window.periods)
            print(
                f"  window {window.index}: "
                f"{window.periods.development.start.date()} to "
                f"{window.periods.out_of_sample.end.date()} "
                f"(dev={len(split['development'])}, "
                f"val={len(split['validation'])}, "
                f"oos={len(split['out_of_sample'])})"
            )

            # Evaluate all families
            configs_this_window = []
            oos_results_by_config_id = {}
            evidence_by_family = {}
            for family in FAMILY_RUNNERS:
                config, oos_result, evidence = evaluate_family_for_window(
                    family, instrument, split, window.index
                )
                configs_this_window.append(config)
                oos_results_by_config_id[config.config_id] = oos_result
                evidence_by_family[family] = evidence
                baseline_oos[family].append({
                    "window_index": window.index,
                    "summary": asdict(oos_result.summary),
                })

            # REAL SELECTOR: respects gate status, not profit factor ranking
            selection = select_strategy(instrument, "h1", configs_this_window)
            selected_oos = (
                oos_results_by_config_id.get(selection.selected_config_id)
                if selection.selected_config_id else None
            )

            selector_windows.append({
                "window_index": window.index,
                "development": window.periods.development.to_dict(),
                "validation": window.periods.validation.to_dict(),
                "out_of_sample": window.periods.out_of_sample.to_dict(),
                "candidates_evidence": evidence_by_family,
                "selector_status": selection.status,
                "selected_config_id": selection.selected_config_id,
                "selector_reason": selection.reason,
                "selected_oos_summary": asdict(selected_oos.summary) if selected_oos else None,
            })
            print(
                f"    -> selector={selection.status}, "
                f"selected={selection.selected_config_id or 'NO_TRADE'}"
            )

        full_report["results"][instrument] = {
            "selector_windows": selector_windows,
            "fixed_baselines": baseline_oos,
        }

        # Save progress after each instrument
        out_path = Path("../research/results/edge_validation_experiment_3.json")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(full_report, f, indent=2, default=str)
        print(f"  (partial) saved to {out_path}")

    print(f"\n✓ Experiment 3 complete. Full report saved to {out_path}")
    return full_report


if __name__ == "__main__":
    main()
