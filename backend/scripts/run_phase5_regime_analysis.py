"""
Phase 5 real-data research run.

Reuses the EXACT same EUR/USD dataset and EXACT same BASE_COST
configuration already validated in Phase 4.5 (unmodified engine,
unmodified strategy) to regenerate the identical baseline trade list
— this is deterministic, so it is byte-for-identical to what Phase 4.5
already produced and saved. This script does not create a new
baseline; it recomputes the same one and joins it with Phase 5's new
feature/regime layer, which did not exist yet in Phase 4.5.

Usage:
    python -m scripts.run_phase5_regime_analysis --csv /path/to/EURUSDh1.csv
"""

import argparse
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from app.backtesting.config import BacktestConfig
from app.backtesting.engine import run_backtest
from app.data_engine.importers.ejtrader_source import (
    EJTRADER_LICENSE, EJTRADER_SOURCE_URL, import_ejtrader_eurusd_h1,
)
from app.data_engine.normalizer import normalize_candles
from app.research.trade_analysis import attach_context_to_trades, group_by_regime, group_by_rsi_zone
from app.technical_engine.features import calculate_feature_snapshots

# Identical to Phase 4.5's BASE_COST configuration — see docs/phase-4-5-real-historical-validation.md
BASE_COST_CONFIG = dict(initial_balance=10000.0, position_size=10000.0, spread=0.00010, slippage=0.00002)


def serialize(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Not JSON serializable: {type(obj)}")


def stats_to_dict(stats_by_label: dict) -> dict:
    return {label: asdict(stats) for label, stats in stats_by_label.items()}


def main():
    parser = argparse.ArgumentParser(description="Phase 5 regime/feature research analysis.")
    parser.add_argument("--csv", required=True)
    parser.add_argument("--output-dir", default="../research/results")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Importing {args.csv} ...")
    candles = normalize_candles(import_ejtrader_eurusd_h1(args.csv))
    print(f"{len(candles)} candles, {candles[0].timestamp} -> {candles[-1].timestamp}")

    print("Recomputing baseline trades (Phase 4/4.5, unmodified, deterministic)...")
    config = BacktestConfig(**BASE_COST_CONFIG)
    backtest_result = run_backtest(candles, config)
    trades = backtest_result.trades
    print(f"{len(trades)} baseline trades")

    print("Computing Phase 5 feature snapshots over the same candles...")
    snapshots = calculate_feature_snapshots(candles)

    contexts = attach_context_to_trades(trades, snapshots)
    matched = sum(1 for c in contexts if c.features is not None)
    print(f"{matched}/{len(contexts)} trades matched to a feature snapshot at signal time")

    by_regime = group_by_regime(contexts)
    by_rsi = group_by_rsi_zone(contexts)

    print("\n=== BY REGIME ===")
    for label, stats in sorted(by_regime.items(), key=lambda kv: -kv[1].trade_count):
        wr = f"{stats.win_rate:.3f}" if stats.win_rate is not None else "n/a"
        pf = f"{stats.profit_factor:.3f}" if stats.profit_factor is not None else "n/a"
        print(f"  {label}: n={stats.trade_count} win_rate={wr} net_pnl={stats.net_pnl:.2f} profit_factor={pf}")

    print("\n=== BY RSI ZONE (at signal time) ===")
    for label, stats in sorted(by_rsi.items(), key=lambda kv: -kv[1].trade_count):
        wr = f"{stats.win_rate:.3f}" if stats.win_rate is not None else "n/a"
        pf = f"{stats.profit_factor:.3f}" if stats.profit_factor is not None else "n/a"
        print(f"  {label}: n={stats.trade_count} win_rate={wr} net_pnl={stats.net_pnl:.2f} profit_factor={pf}")

    # regime distribution over ALL candles (not just trade signal points)
    regime_counts: dict[str, int] = {}
    for s in snapshots:
        regime_counts[s.regime] = regime_counts.get(s.regime, 0) + 1

    output = {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "data_source_url": EJTRADER_SOURCE_URL,
            "data_source_license": EJTRADER_LICENSE,
            "candle_count": len(candles),
            "period_start": candles[0].timestamp.isoformat(),
            "period_end": candles[-1].timestamp.isoformat(),
            "baseline_trade_count": len(trades),
            "trades_matched_to_features": matched,
            "backtest_configuration": BASE_COST_CONFIG,
            "note": "OBSERVED HISTORICAL STATISTICS ONLY — not predictive claims. See docs/phase-5-notes.md.",
        },
        "regime_distribution_all_candles": regime_counts,
        "baseline_trades_by_regime": stats_to_dict(by_regime),
        "baseline_trades_by_rsi_zone": stats_to_dict(by_rsi),
    }

    output_file = output_dir / "phase_5_regime_analysis.json"
    output_file.write_text(json.dumps(output, indent=2, default=serialize))
    print(f"\nSaved to {output_file}")


if __name__ == "__main__":
    main()
