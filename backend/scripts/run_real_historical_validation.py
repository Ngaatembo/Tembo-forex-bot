"""
Reproducible real-historical-data validation for the SMA10/50 crossover
strategy. Runs the UNCHANGED Phase 3 strategy through the UNCHANGED
Phase 4 backtesting engine against real EUR/USD 1H data, across
multiple cost tiers and chronological periods, and writes structured
JSON results to research/results/ for later review.

This script does NOT modify the strategy, optimize parameters, or
select favorable date ranges/costs. Every tier and period below runs
identically and every result is saved, including unfavorable ones.

Usage:
    python -m scripts.run_real_historical_validation \\
        --csv /path/to/EURUSDh1.csv \\
        --initial-balance 10000 \\
        --position-size 10000 \\
        --output-dir ../research/results

The CSV must be in the ejtraderLabs/historical-data format (see
app/data_engine/importers/ejtrader_source.py) — Date,open,high,low,
close,tick_volume with prices scaled x100000. For a different source,
write a new small adapter following that same file as a template
rather than editing this script's parsing logic.
"""

import argparse
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from app.backtesting.config import BacktestConfig
from app.backtesting.engine import run_backtest
from app.backtesting.models import BacktestResult
from app.data_engine.importers.ejtrader_source import (
    EJTRADER_LICENSE, EJTRADER_SOURCE_URL, import_ejtrader_eurusd_h1,
)
from app.data_engine.normalizer import normalize_candles
from app.data_engine.quality_audit import audit_dataset, format_audit_report

COST_TIERS = {
    "ZERO_COST_DIAGNOSTIC": {"spread": 0.0, "slippage": 0.0},
    "LOW_COST": {"spread": 0.00005, "slippage": 0.00001},
    "BASE_COST": {"spread": 0.00010, "slippage": 0.00002},
    "HIGH_COST": {"spread": 0.00020, "slippage": 0.00005},
}


def result_to_dict(result: BacktestResult) -> dict:
    return {
        "configuration": asdict(result.configuration),
        "summary": asdict(result.summary),
        "trades": [asdict(t) for t in result.trades],
        "equity_curve": [asdict(p) for p in result.equity_curve],
    }


def serialize(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Not JSON serializable: {type(obj)}")


def main():
    parser = argparse.ArgumentParser(description="Real historical EUR/USD SMA10/50 validation.")
    parser.add_argument("--csv", required=True)
    parser.add_argument("--initial-balance", type=float, default=10000.0)
    parser.add_argument("--position-size", type=float, default=10000.0)
    parser.add_argument("--output-dir", default="../research/results")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Importing {args.csv} ...")
    candles = normalize_candles(import_ejtrader_eurusd_h1(args.csv))

    audit = audit_dataset(candles, symbol="EUR/USD", timeframe="1h")
    print(format_audit_report(audit))

    run_metadata = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_source_url": EJTRADER_SOURCE_URL,
        "data_source_license": EJTRADER_LICENSE,
        "csv_file": args.csv,
        "symbol": "EUR/USD",
        "timeframe": "1h",
        "candle_count": len(candles),
        "period_start": candles[0].timestamp.isoformat(),
        "period_end": candles[-1].timestamp.isoformat(),
        "strategy": "sma_10_50_crossover (Phase 3, unmodified)",
        "backtest_engine": "Phase 4 (unmodified)",
        "data_quality_audit": {
            "ohlc_violations": len(audit.validation_report.ohlc_violations),
            "zero_or_negative_prices": len(audit.validation_report.negative_or_zero_price),
            "duplicate_timestamps": len(audit.validation_report.duplicate_timestamps),
            "unexpected_gaps": len(audit.validation_report.unexpected_gaps),
            "is_clean": audit.validation_report.is_clean,
        },
    }

    # --- Full-period results across cost tiers ---
    tier_results = {}
    for tier_name, cost_params in COST_TIERS.items():
        config = BacktestConfig(
            initial_balance=args.initial_balance, position_size=args.position_size, **cost_params
        )
        result = run_backtest(candles, config)
        tier_results[tier_name] = result_to_dict(result)
        print(
            f"{tier_name}: trades={result.summary.trade_count} "
            f"return={result.summary.total_return:.4f} "
            f"profit_factor={result.summary.profit_factor}"
        )

    # --- Chronological period split (70/15/15), BASE_COST only ---
    n = len(candles)
    train_end, val_end = int(n * 0.70), int(n * 0.85)
    period_slices = {
        "train_dev": candles[:train_end],
        "validation": candles[train_end:val_end],
        "out_of_sample": candles[val_end:],
    }
    period_results = {}
    for period_name, seg in period_slices.items():
        config = BacktestConfig(
            initial_balance=args.initial_balance, position_size=args.position_size,
            **COST_TIERS["BASE_COST"],
        )
        result = run_backtest(seg, config)
        period_results[period_name] = {
            "period_start": seg[0].timestamp.isoformat(),
            "period_end": seg[-1].timestamp.isoformat(),
            "candle_count": len(seg),
            **result_to_dict(result),
        }
        print(
            f"{period_name}: {seg[0].timestamp.date()}..{seg[-1].timestamp.date()} "
            f"trades={result.summary.trade_count} return={result.summary.total_return:.4f}"
        )

    output = {
        "metadata": run_metadata,
        "cost_tier_results_full_period": tier_results,
        "chronological_period_results_base_cost": period_results,
    }

    output_file = output_dir / "phase_4_5_real_eurusd_validation.json"
    output_file.write_text(json.dumps(output, indent=2, default=serialize))
    print(f"\nSaved full results to {output_file}")


if __name__ == "__main__":
    main()
