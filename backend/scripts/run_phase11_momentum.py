"""
Phase 11 — six pre-registered time-series momentum / trend-following
experiments. T2's threshold (6.0) and max_holding (120 candles) were
calibrated from this dataset's own ratio/duration DISTRIBUTIONS before
any backtest was run — never tuned against a profitability result.
See docs/phase-11-notes.md for the full calibration record.
"""

from app.backtesting.config import BacktestConfig
from app.backtesting.engine_research import simulate_trades_with_exit_rules
from app.backtesting.exit_rules import ExitConfig
from app.data_engine.importers.ejtrader_source import import_ejtrader_eurusd_h1
from app.data_engine.normalizer import normalize_candles
from app.research.periods import EvaluationPeriod, EvaluationPeriods, split_candles_by_period
from app.research.verdict import compute_verdict
from app.strategy_engine.momentum import (
    detect_confirmed_trend_signals, detect_momentum_signals, detect_vol_normalized_signals,
)
from app.technical_engine.features import calculate_feature_snapshots

ATR_STOP_MULTIPLE = 2.0
MAX_HOLDING_CANDLES = 120
T2_THRESHOLD = 6.0
T3_SECONDARY_LOOKBACK = 15  # 60 / 4, per the pre-registered design

COST_TIERS = {
    "LOW": {"spread": 0.00005, "slippage": 0.00001},
    "BASE": {"spread": 0.00010, "slippage": 0.00002},
    "HIGH": {"spread": 0.00020, "slippage": 0.00005},
}
ACCOUNT = {"initial_balance": 10000.0, "position_size": 10000.0}

HYPOTHESES = ["T1_lookback20", "T1_lookback60", "T1_lookback120", "T1_lookback240", "T2_volnorm60", "T3_confirmed60"]


def generate_signals(name: str, candles, features):
    if name == "T1_lookback20":
        return detect_momentum_signals(candles, lookback=20, symbol="EUR/USD")
    if name == "T1_lookback60":
        return detect_momentum_signals(candles, lookback=60, symbol="EUR/USD")
    if name == "T1_lookback120":
        return detect_momentum_signals(candles, lookback=120, symbol="EUR/USD")
    if name == "T1_lookback240":
        return detect_momentum_signals(candles, lookback=240, symbol="EUR/USD")
    if name == "T2_volnorm60":
        return detect_vol_normalized_signals(candles, features, lookback=60, threshold=T2_THRESHOLD, symbol="EUR/USD")
    if name == "T3_confirmed60":
        return detect_confirmed_trend_signals(candles, primary_lookback=60, secondary_lookback=T3_SECONDARY_LOOKBACK, symbol="EUR/USD")
    raise ValueError(name)


def run_one(name, candles, features, cost_key):
    signals = generate_signals(name, candles, features)
    exit_config = ExitConfig(label="momentum_atr_stop_and_max_hold", atr_stop_multiple=ATR_STOP_MULTIPLE, max_holding_candles=MAX_HOLDING_CANDLES)
    config = BacktestConfig(**ACCOUNT, **COST_TIERS[cost_key])
    return simulate_trades_with_exit_rules(candles, signals, features, config, exit_config)


def main():
    csv_path = "/home/claude/real_data/EURUSDh1.csv"
    candles = normalize_candles(import_ejtrader_eurusd_h1(csv_path))
    n = len(candles)
    train_end, val_end = int(n * 0.70), int(n * 0.85)
    periods = EvaluationPeriods(
        development=EvaluationPeriod("development", candles[0].timestamp, candles[train_end].timestamp),
        validation=EvaluationPeriod("validation", candles[train_end].timestamp, candles[val_end].timestamp),
        out_of_sample=EvaluationPeriod("out_of_sample", candles[val_end].timestamp, candles[-1].timestamp),
    )
    split = split_candles_by_period(candles, periods)
    features_by_period = {label: calculate_feature_snapshots(c) for label, c in split.items()}

    results = {}
    for name in HYPOTHESES:
        results[name] = {}
        for tier in COST_TIERS:
            results[name][tier] = {}
            for label in ("development", "validation", "out_of_sample"):
                result = run_one(name, split[label], features_by_period[label], tier)
                results[name][tier][label] = result

        base_periods = {label: results[name]["BASE"][label].summary for label in ("development", "validation", "out_of_sample")}
        verdict = compute_verdict(**base_periods)
        results[name]["verdict_base_cost"] = verdict
        print(f"{name}: verdict={verdict.value}")
        for label in ("development", "validation", "out_of_sample"):
            s = base_periods[label]
            pf = f"{s.profit_factor:.3f}" if s.profit_factor is not None else "n/a"
            print(f"  {label}: trades={s.trade_count} pf={pf} return={s.total_return:.4f}")

    return results, split, features_by_period


if __name__ == "__main__":
    main()
