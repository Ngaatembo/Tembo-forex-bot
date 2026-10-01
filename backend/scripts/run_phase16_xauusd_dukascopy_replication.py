"""Phase 16 — XAU/USD breakout replication on extended Dukascopy H1 data.

The strategy is FROZEN from Phase 13.1: lookbacks 30/40/50, ATR stop 2x,
max holding 100 H1 candles. No parameter selection is performed here.

Purpose:
- replicate the established family on a second data source;
- add genuinely newer calendar data after the old study ended;
- use instrument-appropriate XAU/USD execution costs;
- apply spread/slippage to ATR trigger exits as well as market exits.

This phase cannot promote a strategy to execution.
"""

from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime, timezone

import pandas as pd

from app.backtesting.config import BacktestConfig
from app.backtesting.engine_research import simulate_trades_with_exit_rules
from app.backtesting.exit_rules import ExitConfig
from app.backtesting.models import BacktestSummary
from app.data_engine.market_data import Candle
from app.strategy_engine.breakout import detect_breakout_signals
from app.technical_engine.features import calculate_feature_snapshots
from app.research.statistics_analysis import wilson_confidence_interval, bootstrap_pnl_confidence_interval
from app.research.verdict import compute_verdict

LOOKBACKS = (30, 40, 50)
ATR_STOP_MULTIPLE = 2.0
MAX_HOLDING_CANDLES = 100
POSITION_SIZE = 8.298216860650118  # generalized Phase 13 comparable-notional value

# XAU/USD price-unit costs, not FX pip costs.
COST_TIERS = {
    "LOW": {"spread": 0.20, "slippage": 0.05},
    "BASE": {"spread": 0.40, "slippage": 0.10},
    "HIGH": {"spread": 0.80, "slippage": 0.25},
}

FRESH_START = pd.Timestamp("2022-04-01T00:00:00Z")
FRESH_MID = pd.Timestamp("2024-01-01T00:00:00Z")


def load_data(path: str = "data/xauusd_dukascopy_h1.json") -> pd.DataFrame:
    rows = json.loads(Path(path).read_text())
    df = pd.DataFrame(rows)
    ts_col = "timestamp"
    df["timestamp"] = pd.to_datetime(df[ts_col], unit="ms", utc=True)
    for col in ("open", "high", "low", "close"):
        df[col] = df[col].astype(float)
    return df.sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)


def to_candles(df: pd.DataFrame) -> list[Candle]:
    return [
        Candle(
            symbol="XAU/USD", timeframe="1h", timestamp=r.timestamp.to_pydatetime(),
            open=float(r.open), high=float(r.high), low=float(r.low), close=float(r.close),
        )
        for r in df.itertuples()
    ]


def run(candles, features, lookback, cost_key, start, end):
    subset_candles = candles[start:end]
    subset_features = features[start:end]
    signals = detect_breakout_signals(subset_candles, lookback=lookback, symbol="XAU/USD")
    config = BacktestConfig(
        symbol="XAU/USD", timeframe="1h", initial_balance=10_000.0,
        position_size=POSITION_SIZE, **COST_TIERS[cost_key],
        apply_costs_to_trigger_exits=True,
    )
    exits = ExitConfig(
        label=f"xauusd_breakout_{lookback}_costed",
        atr_stop_multiple=ATR_STOP_MULTIPLE,
        max_holding_candles=MAX_HOLDING_CANDLES,
    )
    return simulate_trades_with_exit_rules(subset_candles, signals, subset_features, config, exits)


def summary(s: BacktestSummary) -> dict:
    return {
        "trade_count": s.trade_count,
        "net_pnl": s.net_pnl,
        "total_return": s.total_return,
        "win_rate": s.win_rate,
        "profit_factor": s.profit_factor,
        "max_drawdown": s.max_drawdown,
        "max_drawdown_percent": s.max_drawdown_percent,
        "average_trade": s.average_trade,
        "average_win": s.average_win,
        "average_loss": s.average_loss,
    }


def period_indices(df):
    return {
        "legacy_overlap": (0, int(df["timestamp"].lt(FRESH_START).sum())),
        "fresh_2022_2024": (
            int(df["timestamp"].lt(FRESH_START).sum()),
            int(df["timestamp"].lt(FRESH_MID).sum()),
        ),
        "fresh_2024_2026": (
            int(df["timestamp"].lt(FRESH_MID).sum()),
            len(df),
        ),
    }


def statistical_summary(result):
    trades = result.trades
    wins = sum(t.net_pnl > 0 for t in trades)
    return {
        "wilson_win_rate_95": wilson_confidence_interval(wins, len(trades)) if trades else None,
        "bootstrap_total_pnl_95": bootstrap_pnl_confidence_interval(
            [t.net_pnl for t in trades], n_resamples=5000, seed=42
        ) if trades else None,
    }


def main():
    df = load_data()
    candles = to_candles(df)
    features = calculate_feature_snapshots(candles)
    periods = period_indices(df)

    out = {
        "source": "Dukascopy historical XAUUSD H1 feed via dukascopy-node",
        "source_coverage_note": "H1 history begins 2003-05-05; fresh replication begins 2022-04-01.",
        "rows": len(df),
        "period_start": df.iloc[0].timestamp.isoformat(),
        "period_end": df.iloc[-1].timestamp.isoformat(),
        "frozen_strategy": {
            "lookbacks": list(LOOKBACKS),
            "atr_stop_multiple": ATR_STOP_MULTIPLE,
            "max_holding_candles": MAX_HOLDING_CANDLES,
            "position_size": POSITION_SIZE,
            "no_parameter_selection": True,
        },
        "cost_tiers": COST_TIERS,
        "periods": {k: {"start_index": v[0], "end_index": v[1]} for k, v in periods.items()},
        "results": {},
    }

    for lookback in LOOKBACKS:
        out["results"][str(lookback)] = {}
        for tier in COST_TIERS:
            out["results"][str(lookback)][tier] = {}
            objects = {}
            for label, (start, end) in periods.items():
                result = run(candles, features, lookback, tier, start, end)
                objects[label] = result
                out["results"][str(lookback)][tier][label] = {
                    "summary": summary(result.summary),
                    "statistics": statistical_summary(result),
                }

            # Descriptive persistence verdict over three fixed periods.
            try:
                out["results"][str(lookback)][tier]["descriptive_verdict"] = compute_verdict(
                    objects["legacy_overlap"].summary,
                    objects["fresh_2022_2024"].summary,
                    objects["fresh_2024_2026"].summary,
                ).value
            except Exception as exc:
                out["results"][str(lookback)][tier]["descriptive_verdict_error"] = str(exc)

    Path("research/results").mkdir(parents=True, exist_ok=True)
    Path("research/results/phase16_xauusd_dukascopy_replication.json").write_text(
        json.dumps(out, indent=2)
    )
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
