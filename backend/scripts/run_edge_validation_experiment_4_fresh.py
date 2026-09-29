"""
Edge Validation Experiment 4 — Stage 2: fresh 2023+ Deriv data.

Stage 1 (edge_validation_experiment_4.json) chose each family's primary
parameter on 2012-2022 validation data. Stage 2 re-tests those EXACT choices
on data none of them has ever seen: Deriv candles from 2023-01-01 to today.
No parameter is re-selected here.

Pre-registered classification of each fixed config on fresh data (BASE costs,
live exits, all of 2023+):
  CONFIRMED       PF >= 1.05 at BASE, PF > 1.00 at HIGH costs, >= 30 trades,
                  and PF > 1.0 in at least half of the calendar years traded
  WEAK            PF > 1.00 at BASE but not CONFIRMED
  FAILED          PF <= 1.00 at BASE
  TOO_FEW_TRADES  fewer than 30 trades

Part B: m5 has no 2012-2022 history, so m5 gets the full Stage 1 treatment
(dev / validation / out-of-sample split and the project's research gate)
inside the 2023+ window instead.

  python -m scripts.run_edge_validation_experiment_4_fresh --data-dir data/deriv \
      --stage1 ../research/results/edge_validation_experiment_4.json \
      --output ../research/results/edge_validation_experiment_4_fresh.json
"""

from __future__ import annotations

import argparse
import ast
import json
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from app.backtesting.config import BacktestConfig
from app.backtesting.engine_research import simulate_trades_with_exit_rules
from app.data_engine.market_data import Candle
from scripts.run_edge_validation_experiment_4 import (
    EURUSD_REFERENCE_PRICE,
    FAMILIES,
    LIVE_EXIT,
    MARKETS,
    brief,
    evaluate_candles,
    signals_for,
)
from app.technical_engine.features import calculate_feature_snapshots

MIN_TRADES = 30


def load_deriv_csv(path: Path, instrument: str, timeframe: str) -> list[Candle]:
    import csv

    rows = []
    with path.open() as fh:
        for r in csv.DictReader(fh):
            rows.append(Candle(instrument, timeframe, datetime.fromisoformat(r["timestamp"]),
                               float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"])))
    return rows


def parse_param(family: str, text: str):
    return ast.literal_eval(text) if family == "sma_crossover" else int(text)


def classify(base, high, yearly_pf) -> str:
    if base.trade_count < MIN_TRADES:
        return "TOO_FEW_TRADES"
    pf, pf_high = base.profit_factor or 0.0, high.profit_factor or 0.0
    if pf <= 1.0:
        return "FAILED"
    years = [v for v in yearly_pf.values() if v is not None]
    good_years = sum(1 for v in years if v > 1.0)
    if pf >= 1.05 and pf_high > 1.0 and years and good_years * 2 >= len(years):
        return "CONFIRMED"
    return "WEAK"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--stage1", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    stage1 = json.loads(Path(args.stage1).read_text())
    data_dir = Path(args.data_dir)

    confirmation = []
    data_coverage = {}
    for cell in stage1["cells"]:
        instrument, tf = cell["instrument"], cell["timeframe"]
        path = data_dir / f"{instrument.replace('/', '')}_{tf}.csv"
        if not path.exists():
            continue
        candles = load_deriv_csv(path, instrument, tf)
        if len(candles) < 200:
            data_coverage[f"{instrument}:{tf}"] = {"candles": len(candles), "note": "too little data"}
            continue
        data_coverage[f"{instrument}:{tf}"] = {"candles": len(candles), "from": candles[0].timestamp.isoformat(), "to": candles[-1].timestamp.isoformat()}
        features = calculate_feature_snapshots(candles)
        _, _, tiers = MARKETS[instrument]
        size = 10_000.0 * EURUSD_REFERENCE_PRICE / statistics.fmean(c.close for c in candles)

        def run(family, param, tier):
            spread, slip = tiers[tier]
            cfg = BacktestConfig(symbol=instrument, timeframe=tf, initial_balance=10_000.0,
                                 position_size=size, spread=spread, slippage=slip)
            return simulate_trades_with_exit_rules(candles, signals_for(family, param, candles, instrument), features, cfg, LIVE_EXIT)

        for family, info in cell.get("families", {}).items():
            primary = parse_param(family, info["primary_param"])
            base, high = run(family, primary, "BASE"), run(family, primary, "HIGH")
            yearly = defaultdict(list)
            for t in base.trades:
                yearly[t.entry_timestamp.year].append(t.net_pnl)
            yearly_pf = {}
            for year, pnls in sorted(yearly.items()):
                gains, losses = sum(p for p in pnls if p > 0), -sum(p for p in pnls if p < 0)
                yearly_pf[str(year)] = round(gains / losses, 3) if losses > 0 else None
            neighbours = {}
            for p in FAMILIES[family]["params"]:
                s = run(family, p, "BASE").summary if p != primary else base.summary
                neighbours[str(p)] = None if s.profit_factor is None else round(s.profit_factor, 3)
            confirmation.append({
                "instrument": instrument, "timeframe": tf, "family": family,
                "primary_param": info["primary_param"],
                "stage1_gate_status": info["gate_status"],
                "stage1_oos_pf": info["out_of_sample"]["profit_factor"],
                "fresh_base": brief(base.summary), "fresh_high_pf": None if high.summary.profit_factor is None else round(high.summary.profit_factor, 3),
                "fresh_yearly_pf": yearly_pf,
                "fresh_neighbourhood_pf": neighbours,
                "fresh_status": classify(base.summary, high.summary, yearly_pf),
            })
            print(f"{instrument} {tf} {family}({info['primary_param']}): stage1 {info['gate_status']} -> fresh {confirmation[-1]['fresh_status']} "
                  f"PF {confirmation[-1]['fresh_base']['profit_factor']} n={base.summary.trade_count} years {yearly_pf}", flush=True)

    m5 = []
    for instrument in MARKETS:
        path = data_dir / f"{instrument.replace('/', '')}_m5.csv"
        if not path.exists():
            continue
        candles = load_deriv_csv(path, instrument, "m5")
        data_coverage[f"{instrument}:m5"] = {"candles": len(candles), "from": candles[0].timestamp.isoformat() if candles else None, "to": candles[-1].timestamp.isoformat() if candles else None}
        cell = evaluate_candles(candles, instrument, "m5", config_prefix="vsc_exp4m5")
        m5.append(cell)
        fams = cell.get("families", {})
        print(f"{instrument} m5 (2023+ split): " + " | ".join(f"{f}: {v['gate_status']} oos PF {v['out_of_sample']['profit_factor']}" for f, v in fams.items()), flush=True)

    Path(args.output).write_text(json.dumps({
        "experiment": "edge_validation_experiment_4_fresh",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_source": "Deriv public API (api.derivws.com), candles from 2023-01-01",
        "classification_rule": classify.__doc__ or "see module docstring",
        "data_coverage": data_coverage,
        "confirmation": confirmation,
        "m5_scan": m5,
    }, indent=1, default=str))
    print("wrote", args.output)


if __name__ == "__main__":
    main()
