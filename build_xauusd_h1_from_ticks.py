"""
Builds hourly XAU/USD mid-price candles (+ median spread per hour) from bid/ask
tick files, for Experiment 3B's 2024+ forward test.

Source: public GitHub repo simom1/XAUUSD-history (monthly Parquet tick files,
columns timestamp/bid/ask, UTC). No licence is published there, so the data
is NOT committed to this repo — rebuild it with:

    git clone --depth 1 https://github.com/simom1/XAUUSD-history.git /tmp/xau
    python -m scripts.build_xauusd_h1_from_ticks /tmp/xau ../data/XAUUSD_H1_2024plus_with_spread.csv

Data-quality fixes applied (all found while running Experiment 3B, 2026-09-25):
- Some files (July 2025 → April 2026) mix in ticks quoted 100x too small
  (e.g. 33.12 instead of 3312). Gold never traded below $500 in this period,
  so any bid/ask below 500 is multiplied by 100. ~32.5M ticks were fixed.
- Ticks with a spread above $5 are dropped as feed errors (~3k ticks).
- 2025/xauusd_2025_10_late.parquet is corrupt in the source and is skipped,
  leaving a gap from 2025-10-20 to 2025-11-02. 2026-04-21 → 05-01 is also
  missing in the source.
- Hours with fewer than 20 ticks are dropped. Where supplementary files
  overlap, the hour with the most ticks wins.

Requires pandas + pyarrow (not in requirements.txt; research-only).
"""

import glob
import os
import sys

import pandas as pd

MIN_PRICE = 500.0
MAX_SPREAD = 5.0
MIN_TICKS_PER_HOUR = 20


def build(src_dir: str, out_csv: str) -> pd.DataFrame:
    bars, skipped = [], []
    for f in sorted(glob.glob(os.path.join(src_dir, "20*", "*.parquet"))):
        try:
            df = pd.read_parquet(f)
        except Exception:
            skipped.append(f)
            continue
        tcol = "timestamp" if "timestamp" in df.columns else "ts"
        df = df[[tcol, "bid", "ask"]].rename(columns={tcol: "ts"})
        for c in ("bid", "ask"):
            low = df[c] < MIN_PRICE
            df.loc[low, c] = df.loc[low, c] * 100
        df = df[(df.ask >= df.bid) & (df.bid > 0)]
        df["spr"] = df.ask - df.bid
        df = df[df.spr <= MAX_SPREAD]
        df["mid"] = (df.bid + df.ask) / 2
        g = df.set_index("ts").resample("1h")
        b = pd.DataFrame({
            "open": g.mid.first(), "high": g.mid.max(), "low": g.mid.min(), "close": g.mid.last(),
            "tick_volume": g.mid.count(), "spread_median": g.spr.median(),
        })
        bars.append(b.dropna(subset=["open"]))
    allb = pd.concat(bars)
    allb = allb.sort_values("tick_volume").groupby(level=0).last().sort_index()
    allb = allb[allb.tick_volume >= MIN_TICKS_PER_HOUR]
    allb.index.name = "Date"
    allb.to_csv(out_csv, date_format="%Y-%m-%dT%H:%M:%S%z")
    print(f"{len(allb)} hourly bars {allb.index.min()} → {allb.index.max()}; skipped: {skipped}")
    return allb


if __name__ == "__main__":
    build(sys.argv[1], sys.argv[2])
