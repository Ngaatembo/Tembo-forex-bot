"""
Phase 8 — structurally different strategy hypotheses.

Both hypotheses below were fixed, with their thresholds chosen, BEFORE
this script was run against validation/out-of-sample data. Threshold
selection used only the FULL dataset's overall distribution (to ensure
each rule fires often enough to be testable at all) — never tuned
against period-specific results. See docs/phase-8-notes.md for the
full pre-registration record.

H1 — Range-Extreme Mean Reversion: price closing very near the edge of
its own recent 20-candle range, while volatility is NOT elevated,
tends to revert. Distinct from Phase 6's RSI-based mean reversion
(different mechanism: range position, not RSI level) and Phase 7's
mean-reversion hypothesis (same distinction).

H2 — Volatility Squeeze Breakout: when the recent 20-candle range
compresses unusually tight, a subsequent move continues in the
direction of the prevailing SMA50 slope. Distinct from every prior
hypothesis — a compression/expansion mechanism, not momentum,
crossover, or RSI.
"""

from app.data_engine.importers.ejtrader_source import (
    EJTRADER_LICENSE, EJTRADER_SOURCE_URL, import_ejtrader_eurusd_h1,
)
from app.data_engine.normalizer import normalize_candles
from app.research.dataset_version import build_dataset_id, compute_file_sha256
from app.research.hypothesis import Condition, Hypothesis, HypothesisType, RuleSet, new_hypothesis_id
from app.research.hypothesis_registry import register_hypothesis
from app.research.periods import EvaluationPeriod, EvaluationPeriods
from app.research.research_experiment import run_research_experiment, save_research_experiment


def build_h1_range_extreme_reversion() -> Hypothesis:
    return Hypothesis(
        id=new_hypothesis_id("range_extreme_reversion"),
        name="Range-Extreme Mean Reversion",
        description=(
            "LONG when close is within 0.0005 (price units) of the recent "
            "20-candle low AND volatility is not elevated (atr_percent < 0.0015). "
            "SHORT is the mirror at the recent high."
        ),
        hypothesis_type=HypothesisType.MEAN_REVERSION,
        market="EUR/USD", timeframe="1h",
        entry_long=RuleSet((
            Condition(field="distance_from_low", operator="<", value=0.0005),
            Condition(field="atr_percent", operator="<", value=0.0015),
        )),
        entry_short=RuleSet((
            Condition(field="distance_from_high", operator="<", value=0.0005),
            Condition(field="atr_percent", operator="<", value=0.0015),
        )),
        risk_conditions={"exit_config": "baseline_opposite_signal"},
        rationale=(
            "Range position (distance from the 20-candle high/low) is a "
            "structurally different mechanism from RSI or SMA crossover — "
            "it directly measures where price sits within its own recent "
            "range rather than a momentum oscillator or a moving-average "
            "relationship. The volatility filter excludes breakout-like "
            "conditions where a range extreme is more likely to continue "
            "than revert."
        ),
        data_requirements=("distance_from_low", "distance_from_high", "atr_percent"),
    )


def build_h2_volatility_squeeze_breakout() -> Hypothesis:
    return Hypothesis(
        id=new_hypothesis_id("volatility_squeeze_breakout"),
        name="Volatility Squeeze Breakout",
        description=(
            "LONG when the 20-candle rolling range compresses below 0.0030 "
            "(price units) AND SMA50 slope is positive. SHORT is the mirror "
            "with negative slope."
        ),
        hypothesis_type=HypothesisType.VOLATILITY,
        market="EUR/USD", timeframe="1h",
        entry_long=RuleSet((
            Condition(field="rolling_range", operator="<", value=0.0030),
            Condition(field="sma_50_slope", operator=">", value=0.0),
        )),
        entry_short=RuleSet((
            Condition(field="rolling_range", operator="<", value=0.0030),
            Condition(field="sma_50_slope", operator="<", value=0.0),
        )),
        risk_conditions={"exit_config": "baseline_opposite_signal"},
        rationale=(
            "A compression in the recent trading range (rolling_range) is a "
            "volatility-structure signal, not a momentum or level-based one. "
            "Combined with a directional bias (SMA50 slope, already present, "
            "not newly computed), the hypothesis is that a squeeze resolves "
            "in the direction of the existing trend — genuinely distinct "
            "from testing SMA crossover or RSI momentum directly."
        ),
        data_requirements=("rolling_range", "sma_50_slope"),
    )


def main():
    csv_path = "/home/claude/real_data/EURUSDh1.csv"
    print(f"Importing {csv_path} ...")
    candles = normalize_candles(import_ejtrader_eurusd_h1(csv_path))
    print(f"{len(candles)} candles, {candles[0].timestamp} -> {candles[-1].timestamp}")

    from app.research.dataset_version import DatasetVersion
    dataset = DatasetVersion(
        dataset_id=build_dataset_id("EUR/USD", "1h", 2012, 2022),
        source=EJTRADER_SOURCE_URL, license=EJTRADER_LICENSE,
        symbol="EUR/USD", timeframe="1h",
        period_start=candles[0].timestamp.isoformat(), period_end=candles[-1].timestamp.isoformat(),
        candle_count=len(candles), import_version="ejtrader_source_v1",
        sha256=compute_file_sha256(csv_path),
    )

    # Same 70/15/15 chronological split used since Phase 4.5/6/7.
    n = len(candles)
    train_end, val_end = int(n * 0.70), int(n * 0.85)
    periods = EvaluationPeriods(
        development=EvaluationPeriod("development", candles[0].timestamp, candles[train_end].timestamp),
        validation=EvaluationPeriod("validation", candles[train_end].timestamp, candles[val_end].timestamp),
        out_of_sample=EvaluationPeriod("out_of_sample", candles[val_end].timestamp, candles[-1].timestamp),
    )

    cost_config = {"spread": 0.00010, "slippage": 0.00002}  # same BASE_COST as every prior phase
    account_config = {"initial_balance": 10000.0, "position_size": 10000.0}

    hyp_registry_path = "/home/claude/ai-trading-platform/research/results/phase_8_hypothesis_registry.json"
    exp_registry_path = "/home/claude/ai-trading-platform/research/results/phase_8_research_experiments.json"

    for build_fn in (build_h1_range_extreme_reversion, build_h2_volatility_squeeze_breakout):
        hypothesis = build_fn()
        registered = register_hypothesis(hypothesis, hyp_registry_path)
        print(f"\n=== {registered.name} ({registered.id}) ===")

        experiment = run_research_experiment(
            registered, candles, dataset, periods, cost_config, account_config
        )
        save_research_experiment(experiment, exp_registry_path)

        for label in ("development", "validation", "out_of_sample"):
            m = experiment.metrics[label]
            pf = m["profit_factor"]
            pf_str = f"{pf:.3f}" if pf is not None else "n/a"
            print(f"  {label:14s}: trades={m['trade_count']:5d}  return={m['total_return']:.4f}  pf={pf_str}")
        print(f"  VERDICT: {experiment.verdict}")


if __name__ == "__main__":
    main()
