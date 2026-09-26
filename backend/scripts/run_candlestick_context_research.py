"""Test whether book-derived candlestick patterns improve when combined
with explicit technical context.

The books emphasize prior trend/context and, for several reversal patterns,
confirmation. This experiment adds only clearly labeled Tembo engineering
filters beyond those book rules:

- RSI: bullish setups require RSI <= 45; bearish setups require RSI >= 55.
- Location: bullish setups must be within 0.5 ATR of the recent 20-bar low;
  bearish setups must be within 0.5 ATR of the recent 20-bar high.

These filters are hypotheses, not claims made by the books. The experiment
compares pattern-only versus pattern-plus-context on chronological
train/validation/out-of-sample splits.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from app.live_engine.candlesticks import detect_candlestick_patterns

DATA_URL = "https://raw.githubusercontent.com/ejtraderLabs/historical-data/main/EURUSD/EURUSDh1.csv"
HORIZONS = (1, 3, 6, 12)
COST_SCENARIOS_PIPS = {"low": 0.5, "base": 1.0, "high": 2.0}
PIP_SIZE = 0.0001
MIN_CANDIDATE_COUNT = 30


def load_data(source: str) -> pd.DataFrame:
    df = pd.read_csv(source)
    df["Date"] = pd.to_datetime(df["Date"], utc=True)
    scale = 100000.0 if df["close"].abs().median() > 10 else 1.0
    for col in ("open", "high", "low", "close"):
        df[col] = df[col].astype(float) / scale
    return df.sort_values("Date").reset_index(drop=True)


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, pd.NA)
    return 100 - (100 / (1 + rs))


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    previous_close = df["close"].shift(1)
    true_range = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - previous_close).abs(),
            (df["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return true_range.rolling(period).mean()


def analyze_split(df: pd.DataFrame, start: int, end: int) -> dict:
    candles = [
        SimpleNamespace(
            open=float(row.open), high=float(row.high),
            low=float(row.low), close=float(row.close),
        )
        for row in df.itertuples()
    ]
    enriched = df.copy()
    enriched["rsi14"] = rsi(enriched["close"])
    enriched["atr14"] = atr(enriched)
    enriched["recent_low20"] = enriched["low"].rolling(20).min().shift(1)
    enriched["recent_high20"] = enriched["high"].rolling(20).max().shift(1)

    rows = []
    for i in range(max(25, start), end):
        patterns = detect_candlestick_patterns(candles[: i + 1])
        for pattern in patterns:
            if pattern.direction == "NEUTRAL":
                continue
            if pattern.confirmation_required and not pattern.confirmed:
                continue

            entry_index = i + 1
            if entry_index >= len(enriched):
                continue

            rsi_value = enriched.iloc[i].rsi14
            atr_value = enriched.iloc[i].atr14
            recent_low = enriched.iloc[i].recent_low20
            recent_high = enriched.iloc[i].recent_high20
            if pd.isna(rsi_value) or pd.isna(atr_value) or atr_value <= 0:
                continue
            if pd.isna(recent_low) or pd.isna(recent_high):
                continue

            close = float(enriched.iloc[i].close)
            near_support = abs(close - float(recent_low)) <= 0.5 * float(atr_value)
            near_resistance = abs(float(recent_high) - close) <= 0.5 * float(atr_value)

            context_ok = (
                (pattern.direction == "BULLISH" and rsi_value <= 45 and near_support)
                or (pattern.direction == "BEARISH" and rsi_value >= 55 and near_resistance)
            )

            entry = float(enriched.iloc[entry_index].open)
            for horizon in HORIZONS:
                exit_index = entry_index + horizon - 1
                if exit_index >= len(enriched):
                    continue
                exit_price = float(enriched.iloc[exit_index].close)
                signed_return = (
                    (exit_price - entry) / entry
                    if pattern.direction == "BULLISH"
                    else (entry - exit_price) / entry
                )
                rows.append(
                    {
                        "pattern": pattern.name,
                        "direction": pattern.direction,
                        "horizon": horizon,
                        "context_ok": bool(context_ok),
                        "signed_return": signed_return,
                    }
                )

    frame = pd.DataFrame(rows)
    if frame.empty:
        return {"pattern_only": {}, "context_filtered": {}}

    def summarize(subset: pd.DataFrame) -> dict:
        result = {}
        for (pattern, direction, horizon), group in subset.groupby(
            ["pattern", "direction", "horizon"]
        ):
            result[f"{pattern}:{direction}:{horizon}h"] = {
                "count": int(len(group)),
                "directional_hit_rate": float((group.signed_return > 0).mean()),
                "average_forward_return": float(group.signed_return.mean()),
                "median_forward_return": float(group.signed_return.median()),
            }
        return result

    return {
        "pattern_only": summarize(frame),
        "context_filtered": summarize(frame[frame.context_ok]),
    }


def main() -> None:
    df = load_data(DATA_URL)
    train_end, validation_end = int(len(df) * 0.70), int(len(df) * 0.85)
    result = {
        "source": DATA_URL,
        "rows": int(len(df)),
        "period": {
            "start": df.iloc[0].Date.isoformat(),
            "end": df.iloc[-1].Date.isoformat(),
        },
        "filters": {
            "bullish_rsi_max": 45,
            "bearish_rsi_min": 55,
            "location_atr_multiple": 0.5,
            "location_lookback": 20,
        },
        "splits": {
            "train": analyze_split(df, 0, train_end),
            "validation": analyze_split(df, train_end, validation_end),
            "out_of_sample": analyze_split(df, validation_end, len(df)),
        },
        "horizons_hours": list(HORIZONS),
        "note": "Historical evidence only; context filters are Tembo engineering hypotheses, not source claims.",
    }
    path = Path("research/results/candlestick_context_research.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
