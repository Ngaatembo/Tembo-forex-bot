"""
Edge Validation Experiment 4 — which market / timeframe has an edge?

Question from the owner: almost every market/timeframe says NO TRADE because
no researched strategy exists for it. Which instrument and timeframe should
Tembo actually trade?

Scope (fixed before running):
  Instruments: EUR/USD, GBP/USD, USD/JPY, XAU/USD
  Timeframes:  m15, h1, h4, d1          (m5 is not in the free dataset)
  Families:    only what the LIVE evaluator can run today —
               breakout (lookback 20/30/40/55), momentum (10/20/40),
               SMA 10/50 trend crossover (neighbours 5/20 and 20/100 for robustness only)
  Exits:       the LIVE exits — ATR(14) stop x2.0, take-profit x4.0 (= 2R),
               max 100 candles. (The research engine also keeps its baseline
               opposite-signal exit.)
  Costs:       per-instrument spreads in PRICE units (LOW / BASE / HIGH).
               Gold uses the measured Experiment 3 costs; JPY in yen.
  Data:        ejtraderLabs/historical-data (Apache-2.0), 2012 → 2022-03.
  Split:       70 / 15 / 15 by candle count: development / validation /
               out-of-sample. The primary parameter is picked on VALIDATION
               profit factor only; out-of-sample is never used for selection.
  Judgement:   the project's own compute_verdict → overfitting diagnostics →
               scorecard → compute_research_gate. Nothing is re-graded here.

Multiple-testing warning (stated up front): ~4 x 4 x 3 = 48 family/market/
timeframe cells are tested. Some will look good by luck. That is why any
survivor must also pass Stage 2 on genuinely fresh 2023+ Deriv data before
it is allowed near the demo account.

Usage:
  python -m scripts.run_edge_validation_experiment_4 --data-dir <ejtrader clone> \
      --output ../research/results/edge_validation_experiment_4.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from app.backtesting.config import BacktestConfig
from app.backtesting.engine_research import simulate_trades_with_exit_rules
from app.backtesting.exit_rules import ExitConfig
from app.data_engine.importers.csv_importer import CSVImportConfig, import_candles_from_csv
from app.data_engine.normalizer import normalize_candles
from app.research.hypothesis import HypothesisType
from app.research.overfitting import compute_overfitting_diagnostics
from app.research.periods import EvaluationPeriod, EvaluationPeriods, split_candles_by_period
from app.research.research_gate import compute_research_gate
from app.research.scorecard import compute_scorecard
from app.research.statistics_analysis import (
    bootstrap_pnl_confidence_interval,
    compute_breakeven_win_rate,
    compute_payoff_stats,
    wilson_confidence_interval,
)
from app.research.verdict import compute_verdict
from app.strategy_engine.breakout import detect_breakout_signals
from app.strategy_engine.crossover import detect_crossover_signals
from app.strategy_engine.momentum import detect_momentum_signals
from app.technical_engine.features import calculate_feature_snapshots
from app.technical_engine.indicators import calculate_sma
from app.technical_engine.models import TechnicalFeature

MARKETS = {
    # instrument: (file prefix, price scale, cost tiers {tier: (spread, slippage)})
    "EUR/USD": ("EURUSD", 1e-5, {"LOW": (0.00005, 0.00001), "BASE": (0.00010, 0.00002), "HIGH": (0.00020, 0.00005)}),
    "GBP/USD": ("GBPUSD", 1e-5, {"LOW": (0.00008, 0.00001), "BASE": (0.00015, 0.00003), "HIGH": (0.00030, 0.00006)}),
    "USD/JPY": ("USDJPY", 1e-3, {"LOW": (0.008, 0.001), "BASE": (0.012, 0.003), "HIGH": (0.025, 0.006)}),
    "XAU/USD": ("XAUUSD", 1e-2, {"LOW": (0.20, 0.02), "BASE": (0.35, 0.05), "HIGH": (0.60, 0.10)}),
}
TIMEFRAMES = ("m15", "h1", "h4", "d1")
LIVE_EXIT = ExitConfig(label="live_atr2_tp4_max100", atr_stop_multiple=2.0, atr_take_profit_multiple=4.0, max_holding_candles=100)
LIVE_EXIT_SUMMARY = {"atr_stop_multiple": 2.0, "atr_take_profit_multiple": 4.0, "max_holding_candles": 100}
FAMILIES = {
    "breakout": {"type": HypothesisType.BREAKOUT, "params": [20, 30, 40, 55]},
    "momentum": {"type": HypothesisType.MOMENTUM, "params": [10, 20, 40]},
    # The live evaluator only runs SMA 10/50, so it is always the primary;
    # the neighbours are used for the robustness score only.
    "sma_crossover": {"type": HypothesisType.TREND_FOLLOWING, "params": [(10, 50), (5, 20), (20, 100)], "fixed_primary": (10, 50)},
}
EURUSD_REFERENCE_PRICE = 1.18  # keeps $ notional comparable across instruments


def load(data_dir: Path, instrument: str, timeframe: str):
    prefix, scale, _ = MARKETS[instrument]
    path = data_dir / prefix / f"{prefix}{timeframe}.csv"
    config = CSVImportConfig(
        timestamp_column="Date", open_column="open", high_column="high", low_column="low", close_column="close",
        volume_column="tick_volume", price_scale=scale, assumed_timezone="UTC",
    )
    return normalize_candles(import_candles_from_csv(str(path), symbol=instrument, timeframe=timeframe, config=config))


def sma_features(candles, fast, slow):
    closes = [c.close for c in candles]
    f, s = calculate_sma(closes, period=fast), calculate_sma(closes, period=slow)
    return [TechnicalFeature(timestamp=c.timestamp, close=c.close, sma_10=f[i], sma_50=s[i]) for i, c in enumerate(candles)]


def signals_for(family, param, candles, symbol):
    if family == "breakout":
        return detect_breakout_signals(candles, lookback=param, symbol=symbol)
    if family == "momentum":
        return detect_momentum_signals(candles, lookback=param, symbol=symbol)
    fast, slow = param
    return detect_crossover_signals(sma_features(candles, fast, slow), symbol=symbol)


def statistical_evidence(trades):
    if not trades:
        return None
    wins = sum(1 for t in trades if t.net_pnl > 0)
    wilson = wilson_confidence_interval(wins, len(trades))
    boot = bootstrap_pnl_confidence_interval([t.net_pnl for t in trades])
    if wilson is None or boot is None:
        return None
    return {
        "wilson_ci": wilson,
        "bootstrap_ci_total_pnl": boot,
        "breakeven_win_rate": compute_breakeven_win_rate(compute_payoff_stats(trades).payoff_ratio),
        "actual_win_rate": wins / len(trades),
    }


def brief(summary):
    return {
        "trades": summary.trade_count,
        "profit_factor": None if summary.profit_factor is None else round(summary.profit_factor, 3),
        "win_rate": None if summary.win_rate is None else round(summary.win_rate, 3),
        "net_pnl": round(summary.net_pnl, 2),
        "return_pct": round(summary.total_return * 100, 2) if summary.total_return is not None else None,
        "max_drawdown_pct": None if summary.max_drawdown_percent is None else round(summary.max_drawdown_percent, 2),
    }


def regime_counts(trades, features):
    by_time = {f.timestamp: f.regime for f in features}
    counts: dict[str, int] = {}
    for t in trades:
        regime = by_time.get(t.signal_timestamp) or by_time.get(t.entry_timestamp) or "UNKNOWN"
        counts[regime] = counts.get(regime, 0) + 1
    return counts


def run_cell(args):
    data_dir, instrument, timeframe = args
    return evaluate_candles(load(Path(data_dir), instrument, timeframe), instrument, timeframe)


def evaluate_candles(candles, instrument, timeframe, config_prefix="vsc_exp4"):
    """Full dev/val/oos evaluation of every family on one market/timeframe."""
    started = time.time()
    n = len(candles)
    if n < 2000:
        return {"instrument": instrument, "timeframe": timeframe, "error": f"only {n} candles"}
    a, b = int(n * 0.70), int(n * 0.85)
    periods = EvaluationPeriods(
        development=EvaluationPeriod("development", candles[0].timestamp, candles[a].timestamp),
        validation=EvaluationPeriod("validation", candles[a].timestamp, candles[b].timestamp),
        out_of_sample=EvaluationPeriod("out_of_sample", candles[b].timestamp, candles[-1].timestamp),
    )
    split = split_candles_by_period(candles, periods)
    feats = {k: calculate_feature_snapshots(v) for k, v in split.items()}
    _, _, tiers = MARKETS[instrument]
    mean_close = statistics.fmean(c.close for c in candles)
    size = 10_000.0 * EURUSD_REFERENCE_PRICE / mean_close

    def run(family, param, label, tier="BASE"):
        spread, slip = tiers[tier]
        cfg = BacktestConfig(symbol=instrument, timeframe=timeframe, initial_balance=10_000.0,
                             position_size=size, spread=spread, slippage=slip)
        sigs = signals_for(family, param, split[label], instrument)
        return simulate_trades_with_exit_rules(split[label], sigs, feats[label], cfg, LIVE_EXIT)

    cell = {
        "instrument": instrument, "timeframe": timeframe, "candles": n,
        "periods": {k: [split[k][0].timestamp.isoformat(), split[k][-1].timestamp.isoformat()] for k in split},
        "position_size": size, "families": {},
    }
    configs = []
    for family, spec in FAMILIES.items():
        per = {p: {lab: run(family, p, lab) for lab in ("development", "validation", "out_of_sample")} for p in spec["params"]}

        def val_pf(p):
            s = per[p]["validation"].summary
            return s.profit_factor if (s.profit_factor is not None and s.trade_count > 0) else float("-inf")

        primary = spec.get("fixed_primary") or max(spec["params"], key=val_pf)
        dev, val, oos = (per[primary][lab].summary for lab in ("development", "validation", "out_of_sample"))
        verdict = compute_verdict(dev, val, oos)
        over = compute_overfitting_diagnostics(dev, val, oos)
        tiers_oos = {"BASE": oos, **{t: run(family, primary, "out_of_sample", t).summary for t in ("LOW", "HIGH")}}
        scorecard = compute_scorecard(
            period_summaries={"development": dev, "validation": val, "out_of_sample": oos},
            verdict=verdict, overfitting=over,
            parameter_neighborhood=[per[p]["out_of_sample"].summary for p in spec["params"]],
            cost_tier_summaries=tiers_oos,
            statistical_evidence=statistical_evidence(per[primary]["out_of_sample"].trades),
            regime_dependence=None,
        )
        gate = compute_research_gate(verdict, scorecard, over)
        all_trades = [t for lab in ("development", "validation", "out_of_sample") for t in per[primary][lab].trades]
        all_feats = feats["development"] + feats["validation"] + feats["out_of_sample"]
        regimes = regime_counts(all_trades, all_feats)
        cell["families"][family] = {
            "primary_param": str(primary),
            "development": brief(dev), "validation": brief(val), "out_of_sample": brief(oos),
            "oos_cost_tiers_pf": {t: (None if s.profit_factor is None else round(s.profit_factor, 3)) for t, s in tiers_oos.items()},
            "neighbourhood_oos_pf": {str(p): (None if per[p]["out_of_sample"].summary.profit_factor is None else round(per[p]["out_of_sample"].summary.profit_factor, 3)) for p in spec["params"]},
            "verdict": verdict.value,
            "gate_status": gate.status,
            "gate_reason": gate.reason,
            "scorecard_levels": {k: getattr(scorecard, k).level for k in ("edge", "robustness", "risk", "statistical", "realism")},
            "regime_evidence": regimes,
        }
        if gate.status in ("PAPER_CANDIDATE", "PROMISING"):
            param_dict = {"lookback": primary} if family != "sma_crossover" else {"fast": 10, "slow": 50}
            configs.append({
                "config_id": f"{config_prefix}_{instrument.replace('/', '').lower()}_{timeframe}_{family}_{str(primary).replace(', ', '_').strip('()')}",
                "candidate_id": f"exp4_{family}_lookback_{primary}" if family != "sma_crossover" else "exp4_sma_crossover_10_50",
                "instrument": instrument, "timeframe": timeframe,
                "strategy_family": spec["type"].value,
                "parameters": param_dict,
                "exit_config_summary": LIVE_EXIT_SUMMARY,
                "cost_assumptions": {"tier": "BASE", "spread": tiers["BASE"][0], "slippage": tiers["BASE"][1]},
                "evidence_period_start": split["development"][0].timestamp.isoformat(),
                "evidence_period_end": split["out_of_sample"][-1].timestamp.isoformat(),
                "gate_status": gate.status, "verdict": verdict.value,
                "statistical_level": scorecard.statistical.level,
                "regime_evidence": regimes,
            })
    cell["seconds"] = round(time.time() - started, 1)
    cell["candidate_configs"] = configs
    return cell


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--only", default="", help="comma list like XAU/USD:h1 to limit cells")
    args = ap.parse_args()
    jobs = [(args.data_dir, i, tf) for i in MARKETS for tf in TIMEFRAMES]
    if args.only:
        wanted = set(args.only.split(","))
        jobs = [j for j in jobs if f"{j[1]}:{j[2]}" in wanted]
    results = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for cell in pool.map(run_cell, jobs):
            results.append(cell)
            fams = cell.get("families", {})
            line = " | ".join(f"{f}: {v['gate_status']} (oos PF {v['out_of_sample']['profit_factor']}, n={v['out_of_sample']['trades']})" for f, v in fams.items())
            print(f"{cell['instrument']} {cell['timeframe']}: {line or cell.get('error')}", flush=True)
    out = {
        "experiment": "edge_validation_experiment_4",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_source": "https://github.com/ejtraderLabs/historical-data (Apache-2.0)",
        "exit": LIVE_EXIT_SUMMARY,
        "cost_tiers": {k: v[2] for k, v in MARKETS.items()},
        "cells": results,
    }
    Path(args.output).write_text(json.dumps(out, indent=1, default=str))
    print("wrote", args.output)


if __name__ == "__main__":
    sys.exit(main())
