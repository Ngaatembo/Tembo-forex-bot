"""
Phase 13 — market/timeframe discovery. Timeframe held constant at 1H
(every existing strategy's thresholds were calibrated against EUR/USD
1H's own distributions — varying timeframe and instrument together
would confound the test). Two instruments selected: GBP/USD (closest
structural analog to EUR/USD) and XAU/USD (deliberately the most
different available asset).

Three strategies reused EXACTLY as already established, no
re-optimization:
  H1 — original unmodified rule (distance=0.0005, atr_ceiling=0.0015)
  Breakout — established 40-candle configuration (Phase 9's central value)
  Momentum — T1 lookback=60

DOCUMENTED TRANSFER LIMITATION (stated before running, not discovered
after): H1's entry uses ABSOLUTE price-unit thresholds calibrated to
EUR/USD's ~1.10 price scale. On XAU/USD (~1500-2000), 0.0005 is likely
too small to ever fire meaningfully. This is reported as a finding,
not silently patched — the rule is not "fixed" for the new instrument.
"""

import sys

from app.backtesting.config import BacktestConfig
from app.backtesting.engine_research import simulate_trades_with_exit_rules
from app.backtesting.exit_rules import ExitConfig
from app.data_engine.importers.csv_importer import import_candles_from_csv
from app.data_engine.importers.ejtrader_source import ejtrader_import_config, ejtrader_xauusd_import_config
from app.data_engine.normalizer import normalize_candles
from app.research.periods import EvaluationPeriod, EvaluationPeriods, split_candles_by_period
from app.research.verdict import compute_verdict
from app.strategy_engine.breakout import detect_breakout_signals
from app.strategy_engine.momentum import detect_momentum_signals
from app.technical_engine.features import calculate_feature_snapshots

sys.path.insert(0, "scripts")

COST_TIERS = {
    "LOW": {"spread": 0.00005, "slippage": 0.00001},
    "BASE": {"spread": 0.00010, "slippage": 0.00002},
    "HIGH": {"spread": 0.00020, "slippage": 0.00005},
}
ACCOUNT = {"initial_balance": 10000.0, "position_size": 10000.0}

# POSITION-SIZING SCALE CORRECTION — a real bug found while running this
# phase: a fixed unit-count position_size (10,000, established for
# EUR/USD at ~1.10) represents wildly different DOLLAR notional
# exposure depending on instrument price scale — ~$11,800 for EUR/USD,
# but ~$85M for XAU/USD at ~1,423 average. Every dollar-denominated
# metric (return%, drawdown%, net P&L) is meaningless without
# correcting for this. Profit factor and win rate are unaffected
# (scale-invariant ratios), which is how the bug was caught: PF looked
# sane, returns of 45,810% did not. Corrected position_size derived
# from each instrument's own mean close price, keeping notional
# exposure comparable to EUR/USD's ~$11,800 average.
XAU_POSITION_SIZE = 8.298216860650118  # 10,000 * (EURUSD_mean / XAUUSD_mean), computed from real data

ACCOUNT_BY_MARKET = {
    "GBP/USD": {"initial_balance": 10000.0, "position_size": 10000.0},  # same price-scale order as EUR/USD, no correction needed
    "XAU/USD": {"initial_balance": 10000.0, "position_size": XAU_POSITION_SIZE},
}

MARKETS = {
    "GBP/USD": {"csv": "/home/claude/real_data/GBPUSDh1.csv", "config": ejtrader_import_config()},
    "XAU/USD": {"csv": "/home/claude/real_data/XAUUSDh1.csv", "config": ejtrader_xauusd_import_config()},
}

STRATEGIES = ["H1", "Breakout40", "Momentum_T1_60"]


def h1_signals(candles, features, symbol):
    from app.research.rule_signal_generator import generate_signals_from_hypothesis
    from run_phase8_hypotheses import build_h1_range_extreme_reversion
    hypothesis = build_h1_range_extreme_reversion()
    return generate_signals_from_hypothesis(hypothesis, candles, features)


def strategy_signals(name, candles, features, symbol):
    if name == "H1":
        return h1_signals(candles, features, symbol)
    if name == "Breakout40":
        return detect_breakout_signals(candles, lookback=40, symbol=symbol)
    if name == "Momentum_T1_60":
        return detect_momentum_signals(candles, lookback=60, symbol=symbol)
    raise ValueError(name)


def exit_config_for(name):
    if name == "H1":
        return ExitConfig(label="baseline")
    if name == "Breakout40":
        return ExitConfig(label="breakout_exit", atr_stop_multiple=2.0, max_holding_candles=100)
    return ExitConfig(label="momentum_exit", atr_stop_multiple=2.0, max_holding_candles=120)


def run_one(name, signals, candles, features, cost_key, symbol):
    config = BacktestConfig(**ACCOUNT_BY_MARKET[symbol], **COST_TIERS[cost_key])
    return simulate_trades_with_exit_rules(candles, signals, features, config, exit_config_for(name))


def main():
    all_results = {}
    for symbol, market_info in MARKETS.items():
        candles = normalize_candles(
            import_candles_from_csv(market_info["csv"], symbol=symbol, timeframe="1h", config=market_info["config"])
        )
        print(f"\n########## {symbol} — {len(candles)} candles ##########")

        n = len(candles)
        train_end, val_end = int(n * 0.70), int(n * 0.85)
        periods = EvaluationPeriods(
            development=EvaluationPeriod("development", candles[0].timestamp, candles[train_end].timestamp),
            validation=EvaluationPeriod("validation", candles[train_end].timestamp, candles[val_end].timestamp),
            out_of_sample=EvaluationPeriod("out_of_sample", candles[val_end].timestamp, candles[-1].timestamp),
        )
        split = split_candles_by_period(candles, periods)
        features_by_period = {label: calculate_feature_snapshots(c) for label, c in split.items()}

        all_results[symbol] = {}
        for strat_name in STRATEGIES:
            all_results[symbol][strat_name] = {}
            signals_by_period = {
                label: strategy_signals(strat_name, split[label], features_by_period[label], symbol)
                for label in ("development", "validation", "out_of_sample")
            }
            for tier in COST_TIERS:
                all_results[symbol][strat_name][tier] = {}
                for label in ("development", "validation", "out_of_sample"):
                    r = run_one(strat_name, signals_by_period[label], split[label], features_by_period[label], tier, symbol)
                    all_results[symbol][strat_name][tier][label] = r

            base = {l: all_results[symbol][strat_name]["BASE"][l].summary for l in ("development", "validation", "out_of_sample")}
            verdict = compute_verdict(**base)
            all_results[symbol][strat_name]["verdict_base_cost"] = verdict
            print(f"\n=== {symbol} / {strat_name} === verdict={verdict.value}")
            for label in ("development", "validation", "out_of_sample"):
                s = base[label]
                pf = f"{s.profit_factor:.3f}" if s.profit_factor else "n/a"
                print(f"  {label}: trades={s.trade_count} pf={pf} return={s.total_return:.4f}")

    return all_results


if __name__ == "__main__":
    main()
