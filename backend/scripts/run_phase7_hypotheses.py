"""
Phase 7 example research hypotheses — momentum, mean-reversion, and
breakout. These are EXAMPLES exercising the research architecture,
not claims that any of them work. Formalized as deterministic
Hypothesis rules before this script ever ran, evaluated identically
against the same real EUR/USD dataset already used since Phase 4.5.

All three were fixed before looking at validation/out-of-sample
results — no threshold here was adjusted after seeing an outcome.
"""

import argparse
from pathlib import Path

from app.data_engine.importers.ejtrader_source import (
    EJTRADER_LICENSE, EJTRADER_SOURCE_URL, import_ejtrader_eurusd_h1,
)
from app.data_engine.normalizer import normalize_candles
from app.research.dataset_version import DatasetVersion, build_dataset_id, compute_file_sha256
from app.research.hypothesis import Condition, Hypothesis, HypothesisType, RuleSet, new_hypothesis_id
from app.research.hypothesis_registry import register_hypothesis
from app.research.periods import EvaluationPeriod, EvaluationPeriods
from app.research.research_experiment import run_research_experiment, save_research_experiment

# --- Hypothesis A: Momentum ---
# Concept: sustained RSI strength/weakness, combined with SMA50 trend
# direction, may persist short-term.
MOMENTUM = Hypothesis(
    id="momentum_rsi_trend_v1", name="RSI + SMA50 Trend Momentum",
    description="Enter long when RSI14>60 while price trends above a rising SMA50; mirror for short.",
    hypothesis_type=HypothesisType.MOMENTUM, market="EUR/USD", timeframe="1h",
    entry_long=RuleSet(conditions=(
        Condition(field="rsi_14", operator=">", value=60.0),
        Condition(field="close", operator=">", compare_field="sma_50"),
        Condition(field="sma_50_slope", operator=">", value=0.0),
    )),
    entry_short=RuleSet(conditions=(
        Condition(field="rsi_14", operator="<", value=40.0),
        Condition(field="close", operator="<", compare_field="sma_50"),
        Condition(field="sma_50_slope", operator="<", value=0.0),
    )),
    risk_conditions={"exit_config": "baseline_reverse_only"},
    rationale="Momentum persisting in the direction of an already-established trend is a common, "
              "economically-motivated (not data-mined) hypothesis distinct from the SMA10/50 crossover control.",
    data_requirements=("rsi_14", "sma_50", "sma_50_slope"),
)

# --- Hypothesis B: Mean Reversion ---
# Concept: price pinned near its recent range extreme with an extreme
# RSI reading may revert toward the middle of the range.
MEAN_REVERSION = Hypothesis(
    id="mean_reversion_range_extreme_v1", name="Range-Extreme Mean Reversion",
    description="Enter long when price is near the recent 20-candle low with RSI14<30; mirror for short near the high.",
    hypothesis_type=HypothesisType.MEAN_REVERSION, market="EUR/USD", timeframe="1h",
    entry_long=RuleSet(conditions=(
        Condition(field="distance_from_low", operator="<", value=0.0010),
        Condition(field="rsi_14", operator="<", value=30.0),
    )),
    entry_short=RuleSet(conditions=(
        Condition(field="distance_from_high", operator="<", value=0.0010),
        Condition(field="rsi_14", operator=">", value=70.0),
    )),
    risk_conditions={"exit_config": "baseline_reverse_only"},
    rationale="A classic mean-reversion premise: extreme short-term moves against a recent range "
              "may revert, distinct in mechanism from both the crossover baseline and the momentum hypothesis.",
    data_requirements=("distance_from_low", "distance_from_high", "rsi_14"),
)

# --- Hypothesis C: Breakout ---
# Concept: price breaking a well-defined recent range, with volatility
# expansion present, may continue in the breakout direction.
BREAKOUT = Hypothesis(
    id="breakout_range_expansion_v1", name="Range Breakout with Volatility Expansion",
    description="Enter long when close exceeds the recent 20-candle high with above-median volatility; mirror for short.",
    hypothesis_type=HypothesisType.BREAKOUT, market="EUR/USD", timeframe="1h",
    entry_long=RuleSet(conditions=(
        Condition(field="close", operator=">", compare_field="recent_high"),
        Condition(field="atr_percent", operator=">", value=0.0008),
    )),
    entry_short=RuleSet(conditions=(
        Condition(field="close", operator="<", compare_field="recent_low"),
        Condition(field="atr_percent", operator=">", value=0.0008),
    )),
    risk_conditions={"exit_config": "baseline_reverse_only"},
    rationale="Breakouts accompanied by genuine volatility expansion are a structurally different "
              "premise from both momentum-persistence and mean-reversion, testing whether range breaks "
              "with confirming volatility continue rather than immediately fail.",
    data_requirements=("recent_high", "recent_low", "atr_percent"),
)

HYPOTHESES = [MOMENTUM, MEAN_REVERSION, BREAKOUT]


def main():
    parser = argparse.ArgumentParser(description="Run Phase 7 example hypotheses against real data.")
    parser.add_argument("--csv", required=True)
    parser.add_argument("--output-dir", default="../research/results")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    hypothesis_registry = str(output_dir / "phase_7_hypothesis_registry.json")
    experiment_registry = str(output_dir / "phase_7_research_experiments.json")

    print(f"Importing {args.csv} ...")
    candles = normalize_candles(import_ejtrader_eurusd_h1(args.csv))
    print(f"{len(candles)} candles, {candles[0].timestamp} -> {candles[-1].timestamp}")

    sha256 = compute_file_sha256(args.csv)
    dataset = DatasetVersion(
        dataset_id=build_dataset_id("EUR/USD", "1h", 2012, 2022, version=1),
        source=EJTRADER_SOURCE_URL, license=EJTRADER_LICENSE,
        symbol="EUR/USD", timeframe="1h",
        period_start=candles[0].timestamp.isoformat(), period_end=candles[-1].timestamp.isoformat(),
        candle_count=len(candles), import_version="ejtrader_v1", sha256=sha256,
    )

    # Same chronological 70/15/15 split as Phase 4.5/6, defined BEFORE
    # any hypothesis result is seen.
    n = len(candles)
    train_end, val_end = int(n * 0.70), int(n * 0.85)
    periods = EvaluationPeriods(
        development=EvaluationPeriod("development", candles[0].timestamp, candles[train_end].timestamp),
        validation=EvaluationPeriod("validation", candles[train_end].timestamp, candles[val_end].timestamp),
        out_of_sample=EvaluationPeriod("out_of_sample", candles[val_end].timestamp,
                                         candles[-1].timestamp + __import__("datetime").timedelta(hours=1)),
    )

    cost_config = {"spread": 0.00010, "slippage": 0.00002}  # same BASE_COST as Phase 4.5/6
    account_config = {"initial_balance": 10000.0, "position_size": 10000.0}

    for hypothesis in HYPOTHESES:
        print(f"\n=== {hypothesis.name} ({hypothesis.id}) ===")
        register_hypothesis(hypothesis, hypothesis_registry)

        experiment = run_research_experiment(
            hypothesis, candles, dataset, periods, cost_config, account_config
        )
        save_research_experiment(experiment, experiment_registry)

        for label in ("development", "validation", "out_of_sample"):
            m = experiment.metrics[label]
            pf = f"{m['profit_factor']:.3f}" if m["profit_factor"] is not None else "n/a"
            print(f"  {label:14s}: trades={m['trade_count']:4d}  return={m['total_return']:8.4f}  pf={pf}")
        print(f"  VERDICT: {experiment.verdict}")

    print(f"\nSaved hypotheses to {hypothesis_registry}")
    print(f"Saved experiments to {experiment_registry}")


if __name__ == "__main__":
    main()
