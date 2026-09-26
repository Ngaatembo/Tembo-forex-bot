"""Phase 10 — Bearish Engulfing strategy research.

Research only. This script does not place orders and cannot promote a
strategy to execution.

Protocol:
1. Detect the existing book-derived BEARISH_ENGULFING observation only
   after the signal candle has closed.
2. Enter at the next candle's open through the existing research engine.
3. Compare four PRE-DECLARED entry variants:
   - pattern_only
   - rsi_context: RSI(14) >= 55
   - resistance_context: signal close within 0.5 ATR of prior 20-bar high
   - rsi_and_resistance
4. Sweep a PRE-DECLARED exit grid:
   stop ATR = 1.5/2.0/2.5
   target ATR = 1.0/1.5/2.0
   max hold = 12/24/48 H1 candles
5. Use development to shortlist configurations, validation to select one,
   and OOS exactly once for the selected configuration.
6. Evaluate LOW/BASE/HIGH execution-cost tiers on every split for the
   selected configuration.
7. Run the existing deterministic verdict, overfitting diagnostics,
   scorecard, and bootstrap P&L interval.

The grid is fixed before looking at OOS. OOS is never used for tuning.
All numeric filters are Tembo operationalizations, not quotations from
the source material.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from app.backtesting.config import BacktestConfig
from app.backtesting.engine_research import simulate_trades_with_exit_rules
from app.backtesting.exit_rules import ExitConfig
from app.backtesting.models import BacktestResult
from app.data_engine.market_data import Candle
from app.live_engine.candlesticks import detect_candlestick_patterns
from app.research.overfitting import compute_overfitting_diagnostics
from app.research.scorecard import compute_scorecard
from app.research.statistics_analysis import (
    bootstrap_pnl_confidence_interval,
    compute_payoff_stats,
    wilson_confidence_interval,
)
from app.research.verdict import compute_verdict
from app.strategy_engine.models import Signal
from app.technical_engine.features import calculate_feature_snapshots

DATA_URL = "https://raw.githubusercontent.com/ejtraderLabs/historical-data/main/EURUSD/EURUSDh1.csv"

ENTRY_VARIANTS = (
    "pattern_only",
    "rsi_context",
    "resistance_context",
    "rsi_and_resistance",
)

STOP_ATR_GRID = (1.5, 2.0, 2.5)
TARGET_ATR_GRID = (1.0, 1.5, 2.0)
MAX_HOLD_GRID = (12, 24, 48)

COST_TIERS = {
    "LOW": {"spread": 0.00005, "slippage": 0.00001},
    "BASE": {"spread": 0.00010, "slippage": 0.00002},
    "HIGH": {"spread": 0.00020, "slippage": 0.00005},
}

INITIAL_BALANCE = 10_000.0
POSITION_SIZE = 10_000.0
MIN_TRADES_PER_PERIOD = 10


def load_data(source: str = DATA_URL) -> pd.DataFrame:
    df = pd.read_csv(source)
    df["Date"] = pd.to_datetime(df["Date"], utc=True)
    scale = 100000.0 if df["close"].abs().median() > 10 else 1.0
    for column in ("open", "high", "low", "close"):
        df[column] = df[column].astype(float) / scale
    return df.sort_values("Date").reset_index(drop=True)


def candles_from_frame(df: pd.DataFrame) -> list[Candle]:
    return [
        Candle(
            symbol="EUR/USD",
            timeframe="1h",
            timestamp=row.Date.to_pydatetime(),
            open=float(row.open),
            high=float(row.high),
            low=float(row.low),
            close=float(row.close),
        )
        for row in df.itertuples()
    ]


def build_entry_signals(candles: list[Candle], features) -> dict[str, list[Signal]]:
    signals = {
        variant: [
            Signal(c.timestamp, "EUR/USD", "WAIT", None, None, "No bearish engulfing setup.")
            for c in candles
        ]
        for variant in ENTRY_VARIANTS
    }

    for i in range(len(candles)):
        observations = detect_candlestick_patterns(candles[: i + 1])
        if not any(
            p.name == "BEARISH_ENGULFING" and p.direction == "BEARISH"
            and p.confirmed
            for p in observations
        ):
            continue

        feature = features[i]
        rsi_ok = feature.rsi_14 is not None and feature.rsi_14 >= 55.0
        atr_ok = feature.atr_14 is not None and feature.atr_14 > 0

        # Exclude the signal candle from the resistance calculation.
        start = max(0, i - 20)
        prior = candles[start:i]
        resistance_ok = False
        if atr_ok and len(prior) >= 20:
            prior_high = max(c.high for c in prior)
            resistance_ok = abs(candles[i].close - prior_high) <= 0.5 * feature.atr_14

        checks = {
            "pattern_only": True,
            "rsi_context": rsi_ok,
            "resistance_context": resistance_ok,
            "rsi_and_resistance": rsi_ok and resistance_ok,
        }

        for variant, accepted in checks.items():
            if accepted:
                signals[variant][i] = Signal(
                    candles[i].timestamp,
                    "EUR/USD",
                    "SELL",
                    feature.sma_10,
                    feature.sma_50,
                    f"Bearish Engulfing strategy ({variant}).",
                )

    return signals


def split_ranges(n: int) -> dict[str, tuple[int, int]]:
    train_end = int(n * 0.70)
    validation_end = int(n * 0.85)
    return {
        "development": (0, train_end),
        "validation": (train_end, validation_end),
        "out_of_sample": (validation_end, n),
    }


def run_config(
    candles: list[Candle],
    features,
    signals: list[Signal],
    start: int,
    end: int,
    stop_atr: float,
    target_atr: float,
    max_hold: int,
    tier: str,
) -> BacktestResult:
    config = BacktestConfig(
        symbol="EUR/USD",
        timeframe="1h",
        initial_balance=INITIAL_BALANCE,
        position_size=POSITION_SIZE,
        **COST_TIERS[tier],
    )
    exit_config = ExitConfig(
        label=f"BE_ATR_{stop_atr}_TP_{target_atr}_H{max_hold}",
        atr_stop_multiple=stop_atr,
        atr_take_profit_multiple=target_atr,
        max_holding_candles=max_hold,
    )
    return simulate_trades_with_exit_rules(
        candles[start:end],
        signals[start:end],
        features[start:end],
        config,
        exit_config,
    )


def summary_dict(result: BacktestResult) -> dict:
    s = result.summary
    return {
        "trade_count": s.trade_count,
        "net_pnl": s.net_pnl,
        "total_return": s.total_return,
        "win_rate": s.win_rate,
        "profit_factor": s.profit_factor,
        "max_drawdown": s.max_drawdown,
        "max_drawdown_percent": s.max_drawdown_percent,
        "average_trade": s.average_trade,
        "expectancy": s.expectancy,
        "average_win": s.average_win,
        "average_loss": s.average_loss,
    }


def rank_key(item: dict) -> tuple:
    summary = item["development"]
    pf = summary["profit_factor"] if summary["profit_factor"] is not None else 0.0
    ret = summary["total_return"]
    dd = summary["max_drawdown_percent"]
    return (pf, ret, -(dd if dd is not None else 1.0))


def research() -> dict:
    df = load_data()
    candles = candles_from_frame(df)
    features = calculate_feature_snapshots(candles)
    signals_by_variant = build_entry_signals(candles, features)
    ranges = split_ranges(len(candles))

    candidates = []
    for variant in ENTRY_VARIANTS:
        for stop_atr in STOP_ATR_GRID:
            for target_atr in TARGET_ATR_GRID:
                for max_hold in MAX_HOLD_GRID:
                    period_results = {}
                    for period, (start, end) in ranges.items():
                        result = run_config(
                            candles, features, signals_by_variant[variant],
                            start, end, stop_atr, target_atr, max_hold, "BASE",
                        )
                        period_results[period] = summary_dict(result)
                    candidates.append({
                        "variant": variant,
                        "stop_atr": stop_atr,
                        "target_atr": target_atr,
                        "max_hold": max_hold,
                        **period_results,
                    })

    # Fixed selection protocol: keep configurations with enough development
    # trades and development PF > 1, then rank by development PF/return.
    eligible = [
        c for c in candidates
        if c["development"]["trade_count"] >= MIN_TRADES_PER_PERIOD
        and (c["development"]["profit_factor"] or 0.0) > 1.0
    ]
    development_shortlist = sorted(eligible, key=rank_key, reverse=True)[:10]

    # Validation selects among the development shortlist. OOS has not been
    # inspected for selection.
    validation_eligible = [
        c for c in development_shortlist
        if c["validation"]["trade_count"] >= MIN_TRADES_PER_PERIOD
        and (c["validation"]["profit_factor"] or 0.0) > 1.0
    ]
    validation_selected = sorted(
        validation_eligible,
        key=lambda c: (
            c["validation"]["profit_factor"] or 0.0,
            c["validation"]["total_return"],
            -(c["validation"]["max_drawdown_percent"] or 1.0),
        ),
        reverse=True,
    )

    selected = validation_selected[0] if validation_selected else None
    result = {
        "protocol": {
            "selection": "Development shortlist (top 10 by development PF/return), then validation confirmation/selection.",
            "oos_policy": "OOS is evaluated only after selection and is never used for parameter tuning.",
            "grid": {
                "entry_variants": list(ENTRY_VARIANTS),
                "stop_atr": list(STOP_ATR_GRID),
                "target_atr": list(TARGET_ATR_GRID),
                "max_hold_candles": list(MAX_HOLD_GRID),
            },
            "minimum_trades_per_period": MIN_TRADES_PER_PERIOD,
        },
        "source": DATA_URL,
        "rows": len(df),
        "period": {
            "start": df.iloc[0].Date.isoformat(),
            "end": df.iloc[-1].Date.isoformat(),
        },
        "candidate_count": len(candidates),
        "development_shortlist": development_shortlist,
        "validation_selected": validation_selected[:5],
        "selected": selected,
    }

    if selected is None:
        result["status"] = "NO_VALIDATION_CANDIDATE"
        result["note"] = "No configuration survived development and validation. No OOS strategy was selected."
        return result

    variant = selected["variant"]
    stop_atr = selected["stop_atr"]
    target_atr = selected["target_atr"]
    max_hold = selected["max_hold"]

    selected_periods = {}
    cost_tiers = {}
    selected_results = {}
    for tier in COST_TIERS:
        tier_results = {}
        for period, (start, end) in ranges.items():
            bt = run_config(
                candles, features, signals_by_variant[variant],
                start, end, stop_atr, target_atr, max_hold, tier,
            )
            tier_results[period] = summary_dict(bt)
            selected_results[f"{tier}:{period}"] = bt
        cost_tiers[tier] = tier_results

    for period in ranges:
        selected_periods[period] = selected_results[f"BASE:{period}"]

    verdict = compute_verdict(
        selected_periods["development"].summary,
        selected_periods["validation"].summary,
        selected_periods["out_of_sample"].summary,
    )
    overfit = compute_overfitting_diagnostics(
        selected_periods["development"].summary,
        selected_periods["validation"].summary,
        selected_periods["out_of_sample"].summary,
    )

    base_trades = selected_periods["out_of_sample"].trades
    payoff = compute_payoff_stats(base_trades)
    win_count = sum(t.net_pnl > 0 for t in base_trades)
    wilson = wilson_confidence_interval(win_count, len(base_trades))
    bootstrap = bootstrap_pnl_confidence_interval(
        [t.net_pnl for t in base_trades],
        n_resamples=5000,
        seed=42,
    )

    tier_summary_objects = {
        tier: selected_results[f"{tier}:out_of_sample"].summary
        for tier in COST_TIERS
    }
    scorecard = compute_scorecard(
        {
            "development": selected_periods["development"].summary,
            "validation": selected_periods["validation"].summary,
            "out_of_sample": selected_periods["out_of_sample"].summary,
        },
        verdict,
        overfit,
        cost_tier_summaries=tier_summary_objects,
        statistical_evidence={
            "trade_count": len(base_trades),
            "win_rate_wilson_95": wilson,
            "bootstrap_total_pnl_95": bootstrap,
        },
    )

    result.update({
        "status": "SELECTED_FOR_OOS",
        "selected": {
            **selected,
            "base_cost_oos": summary_dict(selected_periods["out_of_sample"]),
        },
        "selected_cost_tiers": cost_tiers,
        "verdict_base_cost": verdict.value,
        "overfitting": overfit.__dict__,
        "payoff_stats_oos": payoff.__dict__,
        "wilson_win_rate_95_oos": wilson,
        "bootstrap_total_pnl_95_oos": bootstrap,
        "scorecard": scorecard.to_dict(),
        "note": "Research evidence only. This result does not authorize paper or live execution.",
    })
    return result


def main() -> None:
    output = Path("research/results/phase10_bearish_engulfing_strategy.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    result = research()
    output.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
