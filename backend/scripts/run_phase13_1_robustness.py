"""
Phase 13.1 — robustness of XAU/USD Breakout across the pre-registered
lookback neighborhood 30/40/50. Reuses Phase 13's exact XAU/USD
scale-corrected import and notionally-comparable position sizing.
"""

from app.backtesting.config import BacktestConfig
from app.backtesting.engine_research import simulate_trades_with_exit_rules
from app.backtesting.exit_rules import ExitConfig
from app.data_engine.importers.csv_importer import import_candles_from_csv
from app.data_engine.importers.ejtrader_source import ejtrader_xauusd_import_config
from app.data_engine.normalizer import normalize_candles
from app.research.periods import EvaluationPeriod, EvaluationPeriods, split_candles_by_period
from app.research.verdict import compute_verdict
from app.strategy_engine.breakout import detect_breakout_signals
from app.technical_engine.features import calculate_feature_snapshots

COST_TIERS = {
    "LOW": {"spread": 0.00005, "slippage": 0.00001},
    "BASE": {"spread": 0.00010, "slippage": 0.00002},
    "HIGH": {"spread": 0.00020, "slippage": 0.00005},
}
XAU_POSITION_SIZE = 8.298216860650118
ACCOUNT = {"initial_balance": 10000.0, "position_size": XAU_POSITION_SIZE}
LOOKBACKS = [30, 40, 50]


def run_one(candles, features, lookback, cost_key):
    signals = detect_breakout_signals(candles, lookback=lookback, symbol="XAU/USD")
    exit_config = ExitConfig(label="breakout_exit", atr_stop_multiple=2.0, max_holding_candles=100)
    config = BacktestConfig(**ACCOUNT, **COST_TIERS[cost_key])
    return simulate_trades_with_exit_rules(candles, signals, features, config, exit_config)


def main():
    candles = normalize_candles(
        import_candles_from_csv(
            "/home/claude/real_data/XAUUSDh1.csv", symbol="XAU/USD", timeframe="1h", config=ejtrader_xauusd_import_config(),
        )
    )
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
    for lookback in LOOKBACKS:
        results[lookback] = {}
        for tier in COST_TIERS:
            results[lookback][tier] = {}
            for label in ("development", "validation", "out_of_sample"):
                r = run_one(split[label], features_by_period[label], lookback, tier)
                results[lookback][tier][label] = r
        base = {l: results[lookback]["BASE"][l].summary for l in ("development", "validation", "out_of_sample")}
        verdict = compute_verdict(**base)
        results[lookback]["verdict_base_cost"] = verdict
        print(f"\n=== lookback={lookback} === verdict={verdict.value}")
        for label in ("development", "validation", "out_of_sample"):
            s = base[label]
            pf = f"{s.profit_factor:.3f}" if s.profit_factor else "n/a"
            print(f"  {label}: trades={s.trade_count} pf={pf} return={s.total_return:.4f} max_dd_pct={s.max_drawdown_percent:.4f}")

    return results, split, features_by_period


if __name__ == "__main__":
    main()
