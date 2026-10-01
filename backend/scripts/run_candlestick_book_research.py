"""Empirical test of registered candlestick-book rules on historical OHLC.

Research only. No trades are placed and this script cannot promote a hypothesis.
The experiment uses next-open entry and forward returns at 1/3/6/12 bars.

Important measurement rules:
- gross return is the directional forward return before costs;
- net return subtracts the explicit per-trade cost scenario;
- sample sufficiency is reported per pattern/direction/horizon/split;
- OOS is untouched by selection and is never used to tune thresholds.
"""
from __future__ import annotations
import argparse, json
from pathlib import Path
from types import SimpleNamespace
from math import sqrt
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
    for column in ("open", "high", "low", "close"):
        df[column] = df[column].astype(float) / scale
    return df.sort_values("Date").reset_index(drop=True)

def candles_from_frame(df: pd.DataFrame):
    return [SimpleNamespace(open=float(r.open), high=float(r.high), low=float(r.low), close=float(r.close)) for r in df.itertuples()]

def wilson_interval(successes: int, observations: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if observations <= 0 or successes < 0 or successes > observations:
        raise ValueError("Invalid successes/observations.")
    p = successes / observations
    denominator = 1 + z*z/observations
    centre = (p + z*z/(2*observations)) / denominator
    margin = z * sqrt((p*(1-p)/observations) + (z*z/(4*observations*observations))) / denominator
    return max(0.0, centre-margin), min(1.0, centre+margin)

def net_return(signed_return: float, entry_price: float, cost_pips: float) -> float:
    if entry_price <= 0 or cost_pips < 0:
        raise ValueError("Invalid entry price or cost.")
    return signed_return - ((cost_pips * PIP_SIZE) / entry_price)

def summarize(group: pd.DataFrame) -> dict:
    count = int(len(group))
    gross = group.signed_return
    costs = {}
    for name, pips in COST_SCENARIOS_PIPS.items():
        net = gross - ((pips * PIP_SIZE) / group.entry_price)
        costs[name] = {
            "cost_pips": pips,
            "average_net_return": float(net.mean()),
            "median_net_return": float(net.median()),
            "hit_rate_after_cost": float((net > 0).mean()),
            "positive_after_cost": int((net > 0).sum()),
        }
    successes = int((gross > 0).sum())
    ci_low, ci_high = wilson_interval(successes, count)
    return {
        "count": count,
        "sample_sufficient": count >= MIN_CANDIDATE_COUNT,
        "minimum_candidate_count": MIN_CANDIDATE_COUNT,
        "directional_hit_rate": float((gross > 0).mean()),
        "wilson_95_low": ci_low,
        "wilson_95_high": ci_high,
        "average_gross_return": float(gross.mean()),
        "median_gross_return": float(gross.median()),
        "worst_gross_return": float(gross.min()),
        "best_gross_return": float(gross.max()),
        "cost_scenarios": costs,
    }

def analyze_split(df: pd.DataFrame, start: int, end: int) -> dict:
    candles = candles_from_frame(df)
    rows = []
    for i in range(max(20, start), end):
        patterns = detect_candlestick_patterns(candles[:i+1])
        for pattern in patterns:
            if pattern.direction == "NEUTRAL" or (pattern.confirmation_required and not pattern.confirmed):
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
                signed_return = ((exit_price-entry)/entry if pattern.direction == "BULLISH" else (entry-exit_price)/entry)
                rows.append({"pattern":pattern.name,"direction":pattern.direction,"horizon":horizon,"signed_return":signed_return,"entry_price":entry})
    if not rows:
        return {"observations":0,"patterns":{}}
    frame=pd.DataFrame(rows)
    result={"observations":int(len(frame)),"patterns":{}}
    for key, group in frame.groupby(["pattern","direction","horizon"]):
        result["patterns"][f"{key[0]}:{key[1]}:{key[2]}h"] = summarize(group)
    return result

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--source",default=DATA_URL)
    parser.add_argument("--output",default="research/results/candlestick_book_research.json")
    args=parser.parse_args()
    df=load_data(args.source)
    train_end, validation_end=int(len(df)*0.70), int(len(df)*0.85)
    result={"source":args.source,"rows":int(len(df)),"period":{"start":df.iloc[0].Date.isoformat(),"end":df.iloc[-1].Date.isoformat()},"splits":{"train":analyze_split(df,0,train_end),"validation":analyze_split(df,train_end,validation_end),"out_of_sample":analyze_split(df,validation_end,len(df))},"horizons_hours":list(HORIZONS),"cost_scenarios_pips":COST_SCENARIOS_PIPS,"minimum_candidate_count":MIN_CANDIDATE_COUNT,"note":"Historical evidence only; no result is a profitability guarantee or execution authorization."}
    path=Path(args.output); path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(result,indent=2)); print(json.dumps(result,indent=2))
if __name__=="__main__":
    main()
