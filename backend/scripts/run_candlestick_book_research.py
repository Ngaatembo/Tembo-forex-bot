"""Empirical test of the uploaded candlestick-book rules on historical OHLC.

Research only. It does not place trades and it does not change the live
decision engine. The source dataset is the public ejtraderLabs historical-data
EUR/USD H1 file already used by Tembo's earlier research.

The experiment uses next-open entry and reports forward returns at 1/3/6/12
bars. Confirmation-required patterns must confirm before the next-open entry.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from app.live_engine.candlesticks import detect_candlestick_patterns

DATA_URL = "https://raw.githubusercontent.com/ejtraderLabs/historical-data/main/EURUSD/EURUSDh1.csv"
HORIZONS = (1, 3, 6, 12)


def load_data(source: str) -> pd.DataFrame:
    df = pd.read_csv(source)
    df["Date"] = pd.to_datetime(df["Date"], utc=True)
    scale = 100000.0 if df["close"].abs().median() > 10 else 1.0
    for column in ("open", "high", "low", "close"):
        df[column] = df[column].astype(float) / scale
    return df.sort_values("Date").reset_index(drop=True)


def candles_from_frame(df: pd.DataFrame):
    return [
        SimpleNamespace(
            open=float(row.open), high=float(row.high),
            low=float(row.low), close=float(row.close),
        )
        for row in df.itertuples()
    ]


def analyze_split(df: pd.DataFrame, start: int, end: int) -> dict:
    candles = candles_from_frame(df)
    rows = []

    for i in range(max(20, start), end):
        patterns = detect_candlestick_patterns(candles[: i + 1])
        for pattern in patterns:
            if pattern.direction == "NEUTRAL":
                continue
            if pattern.confirmation_required and not pattern.confirmed:
                continue
            entry_index = i + 1
            if entry_index >= len(candles):
                continue
            entry = candles[entry_index].open
            for horizon in HORIZONS:
                exit_index = entry_index + horizon - 1
                if exit_index >= len(candles):
                    continue
                exit_price = candles[exit_index].close
                signed_return = (
                    (exit_price - entry) / entry
                    if pattern.direction == "BULLISH"
                    else (entry - exit_price) / entry
                )
                rows.append({
                    "pattern": pattern.name,
                    "direction": pattern.direction,
                    "horizon": horizon,
                    "signed_return": signed_return,
                })

    if not rows:
        return {"observations": 0, "patterns": {}}

    frame = pd.DataFrame(rows)
    result = {"observations": int(len(frame)), "patterns": {}}
    for (pattern, direction, horizon), group in frame.groupby(
        ["pattern", "direction", "horizon"]
    ):
        key = f"{pattern}:{direction}:{horizon}h"
        result["patterns"][key] = {
            "count": int(len(group)),
            "directional_hit_rate": float((group.signed_return > 0).mean()),
            "average_forward_return": float(group.signed_return.mean()),
            "median_forward_return": float(group.signed_return.median()),
            "worst_forward_return": float(group.signed_return.min()),
            "best_forward_return": float(group.signed_return.max()),
        }
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=DATA_URL)
    parser.add_argument(
        "--output",
        default="research/results/candlestick_book_research.json",
    )
    args = parser.parse_args()

    df = load_data(args.source)
    train_end, validation_end = int(len(df) * 0.70), int(len(df) * 0.85)
    result = {
        "source": args.source,
        "rows": int(len(df)),
        "period": {
            "start": df.iloc[0].Date.isoformat(),
            "end": df.iloc[-1].Date.isoformat(),
        },
        "splits": {
            "train": analyze_split(df, 0, train_end),
            "validation": analyze_split(df, train_end, validation_end),
            "out_of_sample": analyze_split(df, validation_end, len(df)),
        },
        "horizons_hours": list(HORIZONS),
        "note": "Historical evidence only; not a profitability guarantee.",
    }
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
