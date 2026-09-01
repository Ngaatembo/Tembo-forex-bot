"""
Edge Validation Experiment 1 — Baseline Walk-Forward Evaluation.

Runs the EXISTING strategy_engine strategies through the EXISTING
walk-forward orchestrator (app.research.walk_forward), against the
EXISTING real historical H1 data (EUR/USD, GBP/USD, XAU/USD,
2012-2022, ejtraderLabs/historical-data, Apache-2.0). No new strategy
logic, no new backtesting engine, no parameter tuning — every
parameter below is reused VERBATIM from prior phases' own confirmed
research (see the comment beside each), not re-decided here.

METHODOLOGICAL NOTE: walk-forward OOS performance is a stronger test
of whether historical performance survives repeated unseen periods.
It is NOT proof of future profitability. This script's own report
classifications (POSITIVE/NEGATIVE/MIXED/INSUFFICIENT_SAMPLE) are
deliberately neutral — never "profitable" — matching the same
discipline already established in app.research.verdict.
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
from app.research.walk_forward import WalkForwardConfig, generate_walk_forward_windows, run_walk_forward
from app.strategy_engine.breakout import detect_breakout_signals
from app.strategy_engine.crossover import detect_crossover_signals
from app.strategy_engine.momentum import detect_momentum_signals
from app.strategy_engine.regime_filter import filter_signals_by_regime
from app.technical_engine.features import calculate_feature_snapshots
from app.technical_engine.service import calculate_features

DATASET_SOURCE = "https://github.com/ejtraderLabs/historical-data"
DATASET_LICENSE = "Apache-2.0"
DATA_PATHS = {
    "EUR/USD": ("/home/claude/real_data/EURUSDh1.csv", ejtrader_import_config()),
    "GBP/USD": ("/home/claude/real_data/GBPUSDh1.csv", ejtrader_import_config()),
    "XAU/USD": ("/home/claude/real_data/XAUUSDh1.csv", ejtrader_xauusd_import_config()),
}

SPREAD = 0.00010
SLIPPAGE = 0.00002
INITIAL_BALANCE = 10000.0
POSITION_SIZE = {
    "EUR/USD": 10_000.0, "GBP/USD": 10_000.0, "XAU/USD": 8.298216860650118,
}

BREAKOUT_LOOKBACK = 40
BREAKOUT_EXIT = ExitConfig(label="atr_2x_max100", atr_stop_multiple=2.0, max_holding_candles=100)
MOMENTUM_LOOKBACK = 20
REGIME_FILTER_SET = {"HIGH_VOLATILITY", "TRENDING_DOWN", "TRENDING_UP"}

WF_CONFIG = WalkForwardConfig(development_days=1000, validation_days=200, out_of_sample_days=200, step_days=200)


def load_candles(instrument: str) -> list:
    path, config = DATA_PATHS[instrument]
    candles = import_candles_from_csv(path, symbol=instrument, timeframe="1h", config=config)
    return normalize_candles(candles)


def make_backtest_config(instrument: str) -> BacktestConfig:
    return BacktestConfig(
        symbol=instrument, timeframe="1h", initial_balance=INITIAL_BALANCE,
        position_size=POSITION_SIZE[instrument], spread=SPREAD, slippage=SLIPPAGE,
    )


def _empty_result(config: BacktestConfig) -> BacktestResult:
    return BacktestResult(configuration=config, summary=compute_metrics([], [], config.initial_balance), trades=[], equity_curve=[])


def sma_crossover_runner(instrument: str):
    def _runner(candles: list, config: BacktestConfig) -> BacktestResult:
        if not candles:
            return _empty_result(config)
        features = calculate_features(candles)
        signals = detect_crossover_signals(features, symbol=instrument)
        return simulate_trades(candles, signals, config)
    return _runner


def breakout_runner(instrument: str):
    def _runner(candles: list, config: BacktestConfig) -> BacktestResult:
        if not candles:
            return _empty_result(config)
        signals = detect_breakout_signals(candles, lookback=BREAKOUT_LOOKBACK, symbol=instrument)
        features = calculate_feature_snapshots(candles)
        return simulate_trades_with_exit_rules(candles, signals, features, config, BREAKOUT_EXIT)
    return _runner


def momentum_runner(instrument: str):
    def _runner(candles: list, config: BacktestConfig) -> BacktestResult:
        if not candles:
            return _empty_result(config)
        signals = detect_momentum_signals(candles, lookback=MOMENTUM_LOOKBACK, symbol=instrument)
        features = calculate_feature_snapshots(candles)
        return simulate_trades_with_exit_rules(candles, signals, features, config, BREAKOUT_EXIT)
    return _runner


def regime_filtered_breakout_runner(instrument: str):
    def _runner(candles: list, config: BacktestConfig) -> BacktestResult:
        if not candles:
            return _empty_result(config)
        raw_signals = detect_breakout_signals(candles, lookback=BREAKOUT_LOOKBACK, symbol=instrument)
        features = calculate_feature_snapshots(candles)
        filtered_signals = filter_signals_by_regime(raw_signals, features, REGIME_FILTER_SET)
        return simulate_trades_with_exit_rules(candles, filtered_signals, features, config, BREAKOUT_EXIT)
    return _runner


STRATEGY_RUNNER_FACTORIES = {
    "sma_crossover": sma_crossover_runner,
    "breakout_40": breakout_runner,
    "momentum_20": momentum_runner,
    "regime_filtered_breakout_40": regime_filtered_breakout_runner,
}


def classify_window(oos_result) -> str:
    if oos_result is None or oos_result.summary.trade_count == 0:
        return "INSUFFICIENT_SAMPLE"
    if oos_result.summary.trade_count < 10:
        return "INSUFFICIENT_SAMPLE"
    if oos_result.summary.net_pnl > 0:
        return "POSITIVE_OOS_RESULT"
    return "NEGATIVE_OOS_RESULT"


def classify_strategy_instrument(window_results) -> str:
    classifications = [classify_window(w.oos_result) for w in window_results]
    substantive = [c for c in classifications if c != "INSUFFICIENT_SAMPLE"]
    if not substantive:
        return "INSUFFICIENT_SAMPLE"
    positive = substantive.count("POSITIVE_OOS_RESULT")
    negative = substantive.count("NEGATIVE_OOS_RESULT")
    if positive == len(substantive):
        return "POSITIVE_OOS_RESULT"
    if negative == len(substantive):
        return "NEGATIVE_OOS_RESULT"
    return "MIXED"


def summarize_window(w) -> dict:
    r = w.oos_result
    return {
        "window_index": w.index,
        "development": w.periods.development.to_dict(),
        "validation": w.periods.validation.to_dict(),
        "out_of_sample": w.periods.out_of_sample.to_dict(),
        "selected_candidate": w.selected_candidate,
        "candidate_validation_scores": w.candidate_scores,
        "oos_trade_count": r.summary.trade_count if r else 0,
        "oos_win_rate": r.summary.win_rate if r else None,
        "oos_profit_factor": r.summary.profit_factor if r else None,
        "oos_expectancy": r.summary.expectancy if r else None,
        "oos_max_drawdown": r.summary.max_drawdown if r else None,
        "oos_net_pnl": r.summary.net_pnl if r else None,
        "oos_total_return": r.summary.total_return if r else None,
        "classification": classify_window(r),
    }


def main():
    generated_at = datetime.now(timezone.utc).isoformat()
    full_report = {
        "generated_at": generated_at,
        "methodology_note": (
            "Walk-forward OOS performance is a stronger test of whether historical "
            "performance survives repeated unseen periods. It is NOT proof of future "
            "profitability. Classifications below are neutral descriptions of what "
            "already happened in this historical data, not predictions."
        ),
        "dataset_source": DATASET_SOURCE, "dataset_license": DATASET_LICENSE,
        "walk_forward_config": {
            "development_days": WF_CONFIG.development_days, "validation_days": WF_CONFIG.validation_days,
            "out_of_sample_days": WF_CONFIG.out_of_sample_days, "step_days": WF_CONFIG.step_days,
        },
        "cost_assumptions": {"spread": SPREAD, "slippage": SLIPPAGE, "tier": "BASE (reused verbatim from Phase 9/9.1/11/13)"},
        "results": {},
    }

    for instrument in ("EUR/USD", "GBP/USD", "XAU/USD"):
        print(f"=== {instrument} ===")
        candles = load_candles(instrument)
        print(f"  loaded {len(candles)} candles, {candles[0].timestamp} to {candles[-1].timestamp}")
        bt_config = make_backtest_config(instrument)

        windows = generate_walk_forward_windows(candles, WF_CONFIG)
        print(f"  {len(windows)} walk-forward windows generated")

        instrument_results = {}
        for strategy_name, factory in STRATEGY_RUNNER_FACTORIES.items():
            candidates = {strategy_name: factory(instrument)}
            report = run_walk_forward(candles, windows, candidates, bt_config)

            window_summaries = [summarize_window(w) for w in report.window_results]
            net_pnls = [w["oos_net_pnl"] for w in window_summaries if w["oos_net_pnl"] is not None]
            profitable_windows = sum(1 for p in net_pnls if p > 0)

            instrument_results[strategy_name] = {
                "windows": window_summaries,
                "aggregate_oos": asdict(report.aggregate),
                "windows_profitable_pct": (profitable_windows / len(net_pnls) * 100) if net_pnls else None,
                "average_oos_net_pnl_per_window": (sum(net_pnls) / len(net_pnls)) if net_pnls else None,
                "worst_oos_window": min(window_summaries, key=lambda w: w["oos_net_pnl"] if w["oos_net_pnl"] is not None else float("inf")),
                "best_oos_window": max(window_summaries, key=lambda w: w["oos_net_pnl"] if w["oos_net_pnl"] is not None else float("-inf")),
                "classification": classify_strategy_instrument(report.window_results),
            }
            print(f"  {strategy_name}: {report.aggregate.total_oos_trades} OOS trades, "
                  f"classification={instrument_results[strategy_name]['classification']}")

        full_report["results"][instrument] = instrument_results

    out_path = "/home/claude/ai-trading-platform/research/results/edge_validation_experiment_1.json"
    with open(out_path, "w") as f:
        json.dump(full_report, f, indent=2, default=str)
    print(f"\nSaved to {out_path}")
    return full_report


if __name__ == "__main__":
    main()
