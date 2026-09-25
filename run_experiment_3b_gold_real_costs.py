"""
Experiment 3B — Gold (XAU/USD) with realistic trading costs + a frozen forward test on 2024–2026.

WHY THIS EXISTS
Every XAU/USD result so far (Phases 13, 13.1, Edge Validation 1 and 2) used the
forex cost tiers (spread 0.0001, slippage 0.00002 in PRICE UNITS). For gold,
quoted around $1,200–$4,300, that is ~$0.0001 per ounce: effectively free
trading. Real gold spreads are ~$0.15–$0.60 per ounce. This script re-tests the
SAME strategies with the SAME engine, changing only the cost assumption, and
then runs the frozen configurations on 2024+ data they have never seen.

NOTHING IS TUNED ON 2024+ DATA. Strategy parameters are exactly the ones
already in research/results/validated_strategy_configs.json (breakout 30/40/50,
ATR 2x stop, 100-candle max hold) plus their existing neighbours.

DATA
- 2012-05 → 2022-03: ejtraderLabs/historical-data XAUUSDh1.csv (Apache-2.0),
  the same file every earlier phase used.
- 2024-01 → 2026-09: hourly mid-price candles built from bid/ask ticks in the
  public GitHub repo simom1/XAUUSD-history (see build script). The same ticks
  give the measured spread. Known gaps: 2025-10-20→11-02 (corrupt source file)
  and 2026-04-21→05-01 (missing in source).

Usage:
    python -m scripts.run_experiment_3b_gold_real_costs \
        --old ../data/XAUUSDh1.csv --new ../data/XAUUSD_H1_2024plus_with_spread.csv \
        --out ../research/results/experiment_3b_gold_real_costs.json
"""

import argparse
import json
import statistics
import sys
from datetime import datetime, timezone

sys.path.insert(0, ".")

from app.backtesting.config import BacktestConfig
from app.backtesting.engine import simulate_trades
from app.backtesting.engine_research import simulate_trades_with_exit_rules
from app.backtesting.exit_rules import ExitConfig
from app.data_engine.importers.csv_importer import CSVImportConfig, import_candles_from_csv
from app.data_engine.importers.ejtrader_source import ejtrader_xauusd_import_config
from app.data_engine.normalizer import normalize_candles
from app.research.statistics_analysis import bootstrap_pnl_confidence_interval
from app.strategy_engine.breakout import detect_breakout_signals
from app.strategy_engine.crossover import detect_crossover_signals
from app.strategy_engine.momentum import detect_momentum_signals
from app.strategy_engine.regime_filter import filter_signals_by_regime
from app.technical_engine.features import calculate_feature_snapshots
from app.technical_engine.indicators import calculate_sma
from app.technical_engine.models import TechnicalFeature

INSTRUMENT = "XAU/USD"
INITIAL_BALANCE = 10_000.0
POSITION_SIZE_OZ = 8.298216860650118  # unchanged from Phase 13 onward

# Spread = full bid/ask spread in $/oz; slippage = $/oz per side.
COST_TIERS = {
    "ORIGINAL_FOREX_TIER": {"spread": 0.00010, "slippage": 0.00002},  # what every earlier gold test used
    "LOW": {"spread": 0.20, "slippage": 0.02},   # raw/ECN account, calm hours (≈ measured median 2024–26)
    "BASE": {"spread": 0.35, "slippage": 0.05},  # typical retail raw account incl. commission equivalent
    "HIGH": {"spread": 0.60, "slippage": 0.10},  # standard account / news hours
}
BREAKOUT_EXIT = ExitConfig(label="atr_2x_max100", atr_stop_multiple=2.0, max_holding_candles=100)
REGIME_FILTER_SET = {"HIGH_VOLATILITY", "TRENDING_DOWN", "TRENDING_UP"}

STRATEGIES = {
    "breakout_20": ("breakout", 20),
    "breakout_30": ("breakout", 30),   # validated config (PROMISING)
    "breakout_40": ("breakout", 40),   # validated config (PROMISING)
    "breakout_50": ("breakout", 50),   # validated config (PROMISING)
    "breakout_60": ("breakout", 60),
    "regime_filtered_breakout_40": ("regime_breakout", 40),
    "momentum_20": ("momentum", 20),
    "sma_crossover_5_20": ("sma", (5, 20)),
}
FROZEN = ("breakout_30", "breakout_40", "breakout_50")


def load_old(path):
    return normalize_candles(import_candles_from_csv(path, symbol=INSTRUMENT, timeframe="1h", config=ejtrader_xauusd_import_config()))


def load_new(path):
    cfg = CSVImportConfig(timestamp_column="Date", open_column="open", high_column="high", low_column="low",
                          close_column="close", volume_column="tick_volume", assumed_timezone="UTC")
    return normalize_candles(import_candles_from_csv(path, symbol=INSTRUMENT, timeframe="1h", config=cfg))


def config_for(tier):
    return BacktestConfig(symbol=INSTRUMENT, timeframe="1h", initial_balance=INITIAL_BALANCE,
                          position_size=POSITION_SIZE_OZ, **COST_TIERS[tier])


def run(name, candles, features, tier):
    kind, p = STRATEGIES[name]
    cfg = config_for(tier)
    if kind == "sma":
        closes = [c.close for c in candles]
        f, s = calculate_sma(closes, period=p[0]), calculate_sma(closes, period=p[1])
        feats = [TechnicalFeature(timestamp=c.timestamp, close=c.close, sma_10=f[i], sma_50=s[i]) for i, c in enumerate(candles)]
        return simulate_trades(candles, detect_crossover_signals(feats, symbol=INSTRUMENT), cfg)
    if kind == "momentum":
        sig = detect_momentum_signals(candles, lookback=p, symbol=INSTRUMENT)
    else:
        sig = detect_breakout_signals(candles, lookback=p, symbol=INSTRUMENT)
        if kind == "regime_breakout":
            sig = filter_signals_by_regime(sig, features, REGIME_FILTER_SET)
    return simulate_trades_with_exit_rules(candles, sig, features, cfg, BREAKOUT_EXIT)


def summarize(res):
    s = res.summary
    avg_cost = statistics.mean(t.transaction_costs for t in res.trades) if res.trades else None
    avg_gross = statistics.mean(t.gross_pnl for t in res.trades) if res.trades else None
    return {
        "trades": s.trade_count,
        "win_rate": s.win_rate,
        "profit_factor": s.profit_factor,
        "expectancy_per_trade": s.expectancy,
        "avg_gross_pnl_per_trade": avg_gross,
        "avg_cost_per_trade": avg_cost,
        "net_pnl": s.net_pnl,
        "total_return": s.total_return,
        "max_drawdown_percent": s.max_drawdown_percent,
    }


def direction_split(res):
    out = {}
    for d in ("LONG", "SHORT"):
        ts = [t for t in res.trades if str(getattr(t.direction, "value", t.direction)).upper() == d]
        wins = sum(t.net_pnl for t in ts if t.net_pnl > 0)
        losses = -sum(t.net_pnl for t in ts if t.net_pnl < 0)
        out[d] = {"trades": len(ts), "net_pnl": sum(t.net_pnl for t in ts),
                  "profit_factor": (wins / losses) if losses > 0 else None}
    return out


def by_half_year(res):
    buckets = {}
    for t in res.trades:
        k = f"{t.exit_timestamp.year}-H{1 if t.exit_timestamp.month <= 6 else 2}"
        buckets.setdefault(k, []).append(t.net_pnl)
    return {k: {"trades": len(v), "net_pnl": round(sum(v), 2)} for k, v in sorted(buckets.items())}


def buy_and_hold(candles, tier):
    c = COST_TIERS[tier]
    entry = candles[0].close + c["spread"] / 2 + c["slippage"]
    exitp = candles[-1].close - c["spread"] / 2 - c["slippage"]
    return {"entry": candles[0].close, "exit": candles[-1].close, "net_pnl": (exitp - entry) * POSITION_SIZE_OZ,
            "note": "Holding the same 8.3 oz position for the whole period, for context only."}


def evaluate(label, candles):
    features = calculate_feature_snapshots(candles)
    block = {"period": [candles[0].timestamp.isoformat(), candles[-1].timestamp.isoformat()], "candles": len(candles),
             "strategies": {}, "buy_and_hold_BASE": buy_and_hold(candles, "BASE")}
    for name in STRATEGIES:
        block["strategies"][name] = {}
        for tier in COST_TIERS:
            res = run(name, candles, features, tier)
            entry = summarize(res)
            if name in FROZEN and tier == "BASE":
                entry["direction_split"] = direction_split(res)
                entry["by_half_year"] = by_half_year(res)
                ci = bootstrap_pnl_confidence_interval([t.net_pnl for t in res.trades]) if res.trades else None
                entry["bootstrap_95ci_total_pnl"] = ci
            block["strategies"][name][tier] = entry
        print(f"[{label}] {name}: " + " | ".join(
            f"{t} PF={block['strategies'][name][t]['profit_factor'] and round(block['strategies'][name][t]['profit_factor'], 3)}"
            f" net={round(block['strategies'][name][t]['net_pnl'])}" for t in COST_TIERS))
    return block


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--old", required=True)
    ap.add_argument("--new", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    old, new = load_old(a.old), load_new(a.new)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "experiment": "3B — gold with realistic costs + frozen forward test 2024–2026",
        "position_size_oz": POSITION_SIZE_OZ,
        "cost_tiers_usd_per_oz": COST_TIERS,
        "exit_rule": "ATR 2x stop, max 100 candles (unchanged)",
        "method_note": "No parameters chosen on 2024+ data. Historical results do not guarantee future profit.",
        "history_2012_2022": evaluate("2012-2022", old),
        "forward_2024_2026": evaluate("2024-2026", new),
    }
    with open(a.out, "w") as f:
        json.dump(report, f, indent=1, default=str)
    print("saved", a.out)


if __name__ == "__main__":
    main()
