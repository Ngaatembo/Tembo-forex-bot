"""
Phase 9 — Market-Structure Breakout Research.

PARAMETER SELECTION, justified before running anything against real
data (per spec section 4's explicit requirement to inspect the
existing codebase before choosing values):

Lookback neighborhood: 20 / 40 / 60 candles.
  - 20 is not an arbitrary starting point — it is the SAME window
    already used for `recent_high`/`recent_low` throughout Phases 5,
    7, and 8 (see technical_engine/features.py::RECENT_HIGH_LOW_WINDOW).
    Using it as breakout's central value keeps this strategy
    comparable in spirit to work already done, rather than introducing
    a brand-new unrelated number.
  - 40 and 60 are 2x/3x multiples of that anchor — also loosely
    consistent with classic Donchian-channel breakout conventions
    (e.g. 20/55-candle lookbacks in the "Turtle Trading" system), an
    independent sanity check that these aren't outlandish choices.

Exit parameters (FIXED, not swept, per spec section 4):
  - ATR stop multiple: 2.0 — reuses Phase 6's exact, already-tested
    `atr_stop_2x` value rather than introducing a new untested number.
  - Max holding: 100 candles (~4.2 days on this 1H timeframe) — roughly
    half of Phase 6's 200-candle cap, which was found to NEVER bind for
    the mean-reversion-flavored crossover strategy (median holding was
    36 hours). Breakout trades are hypothesized to resolve faster than
    a slow crossover reversal, so a tighter — but still generous —
    safety cap is reasoned, not arbitrary. This is a SAFETY NET, not
    the primary exit mechanism; the ATR stop is expected to do most of
    the work.

REMINDER (per spec section 5): the out-of-sample period used here has
already been seen by this project (Phase 4.5 onward). Results on it
are RESEARCH EVIDENCE, not fresh confirmation — the same caveat
already established and respected in Phase 8.1.
"""

from app.backtesting.config import BacktestConfig
from app.backtesting.engine_research import simulate_trades_with_exit_rules
from app.backtesting.exit_rules import ExitConfig
from app.data_engine.importers.ejtrader_source import import_ejtrader_eurusd_h1
from app.data_engine.normalizer import normalize_candles
from app.research.dataset_version import DatasetVersion, build_dataset_id, compute_file_sha256
from app.research.hypothesis import Hypothesis, HypothesisStatus, HypothesisType, RuleSet, new_hypothesis_id
from app.research.hypothesis_registry import register_hypothesis
from app.research.periods import EvaluationPeriod, EvaluationPeriods, split_candles_by_period
from app.research.verdict import compute_verdict
from app.strategy_engine.breakout import detect_breakout_signals
from app.technical_engine.features import calculate_feature_snapshots

LOOKBACK_NEIGHBORHOOD = [20, 40, 60]
ATR_STOP_MULTIPLE = 2.0
MAX_HOLDING_CANDLES = 100
COST_TIERS = {
    "LOW": {"spread": 0.00005, "slippage": 0.00001},
    "BASE": {"spread": 0.00010, "slippage": 0.00002},
    "HIGH": {"spread": 0.00020, "slippage": 0.00005},
}
ACCOUNT = {"initial_balance": 10000.0, "position_size": 10000.0}


def build_breakout_hypothesis(lookback: int) -> Hypothesis:
    """
    entry_long/entry_short are left EMPTY RuleSets — honest, not a
    placeholder pretending this is Condition-evaluable. The actual
    entry logic lives in app.strategy_engine.breakout (see that
    module's docstring for why). This Hypothesis object exists for
    registry/versioning/documentation purposes, matching the project's
    established pattern for the SMA crossover strategy, which is
    likewise not expressed via Condition.
    """
    return Hypothesis(
        id=new_hypothesis_id(f"breakout_lookback_{lookback}"),
        name=f"Market-Structure Breakout (lookback={lookback})",
        description=(
            f"LONG when close breaks above the prior {lookback}-candle high "
            f"(lagged, excluding the signal candle itself). SHORT is the mirror "
            f"at the prior {lookback}-candle low. Exit: ATR stop ({ATR_STOP_MULTIPLE}x, "
            f"frozen at entry) OR max holding ({MAX_HOLDING_CANDLES} candles), OR an "
            f"opposite-direction breakout, whichever comes first."
        ),
        hypothesis_type=HypothesisType.BREAKOUT,
        market="EUR/USD", timeframe="1h",
        entry_long=RuleSet(()), entry_short=RuleSet(()),
        risk_conditions={
            "exit_config": "atr_stop_and_max_hold",
            "atr_stop_multiple": ATR_STOP_MULTIPLE,
            "max_holding_candles": MAX_HOLDING_CANDLES,
            "lookback": lookback,
        },
        rationale=(
            "Structurally distinct from every prior hypothesis: entry is driven "
            "by a LAGGED price-structure threshold (breaking a prior range), not "
            "a moving-average relationship, an oscillator level, or a volatility "
            "compression. This tests whether directional persistence exists "
            "after a decisive break of recent structure."
        ),
        data_requirements=("high", "low", "close", "atr_14"),
        status=HypothesisStatus.REGISTERED,
    )


def run_one(candles, features, lookback, cost_key):
    signals = detect_breakout_signals(candles, lookback=lookback, symbol="EUR/USD")
    exit_config = ExitConfig(
        label="breakout_atr_stop_and_max_hold",
        atr_stop_multiple=ATR_STOP_MULTIPLE, max_holding_candles=MAX_HOLDING_CANDLES,
    )
    config = BacktestConfig(**ACCOUNT, **COST_TIERS[cost_key])
    return simulate_trades_with_exit_rules(candles, signals, features, config, exit_config)


def summarize(label, result):
    s = result.summary
    pf = f"{s.profit_factor:.3f}" if s.profit_factor is not None else "n/a"
    wr = f"{s.win_rate:.3f}" if s.win_rate is not None else "n/a"
    print(f"  {label:28s}: trades={s.trade_count:5d}  return={s.total_return:8.4f}  win_rate={wr}  pf={pf}")


def main():
    csv_path = "/home/claude/real_data/EURUSDh1.csv"
    print(f"Importing {csv_path} ...")
    candles = normalize_candles(import_ejtrader_eurusd_h1(csv_path))
    print(f"{len(candles)} candles, {candles[0].timestamp} -> {candles[-1].timestamp}")

    n = len(candles)
    train_end, val_end = int(n * 0.70), int(n * 0.85)
    periods = EvaluationPeriods(
        development=EvaluationPeriod("development", candles[0].timestamp, candles[train_end].timestamp),
        validation=EvaluationPeriod("validation", candles[train_end].timestamp, candles[val_end].timestamp),
        out_of_sample=EvaluationPeriod("out_of_sample", candles[val_end].timestamp, candles[-1].timestamp),
    )
    split = split_candles_by_period(candles, periods)
    features_by_period = {label: calculate_feature_snapshots(c) for label, c in split.items()}

    dataset = DatasetVersion(
        dataset_id=build_dataset_id("EUR/USD", "1h", 2012, 2022),
        source="https://github.com/ejtraderLabs/historical-data", license="Apache-2.0",
        symbol="EUR/USD", timeframe="1h",
        period_start=candles[0].timestamp.isoformat(), period_end=candles[-1].timestamp.isoformat(),
        candle_count=len(candles), import_version="ejtrader_source_v1",
        sha256=compute_file_sha256(csv_path),
    )

    hyp_registry_path = "/home/claude/ai-trading-platform/research/results/phase_9_hypothesis_registry.json"

    all_results = {}
    for lookback in LOOKBACK_NEIGHBORHOOD:
        hypothesis = build_breakout_hypothesis(lookback)
        register_hypothesis(hypothesis, hyp_registry_path)
        print(f"\n=== lookback={lookback} (id={hypothesis.id}) ===")

        all_results[lookback] = {}
        period_summaries = {}
        for tier in COST_TIERS:
            all_results[lookback][tier] = {}
            print(f" {tier}:")
            for label in ("development", "validation", "out_of_sample"):
                result = run_one(split[label], features_by_period[label], lookback, tier)
                summarize(f"  {label}", result)
                all_results[lookback][tier][label] = result.summary
                if tier == "BASE":
                    period_summaries[label] = result.summary

        verdict = compute_verdict(
            period_summaries["development"], period_summaries["validation"], period_summaries["out_of_sample"]
        )
        print(f" VERDICT (BASE cost): {verdict.value}")
        all_results[lookback]["verdict_base_cost"] = verdict.value

    return all_results, dataset, periods


if __name__ == "__main__":
    main()
