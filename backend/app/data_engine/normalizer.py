"""
Normalization: turn provider-specific candle data into a clean,
consistent set of Candle objects the rest of the system can trust.

This does NOT validate correctness (that's validator.py) — it only
standardizes shape: UTC timestamps, consistent float precision,
de-duplication, and sort order. Validation and normalization are kept
separate on purpose, so a validation failure is always about the data
itself, never about a formatting inconsistency we introduced.
"""

from datetime import timezone

from app.data_engine.market_data import Candle


def normalize_candles(candles: list[Candle], decimals: int = 5) -> list[Candle]:
    """
    - Forces all timestamps to UTC (forex data must never be compared
      across mismatched timezones — a single naive-vs-aware bug here
      would silently corrupt every downstream calculation)
    - Rounds prices to a consistent decimal precision (avoids float
      noise like 1.10000000000002 from provider JSON parsing)
    - Removes exact-duplicate timestamps, keeping the first occurrence
    - Returns candles sorted oldest -> newest
    """
    seen_timestamps: set = set()
    normalized: list[Candle] = []

    for c in candles:
        ts = c.timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        else:
            ts = ts.astimezone(timezone.utc)

        if ts in seen_timestamps:
            continue
        seen_timestamps.add(ts)

        normalized.append(
            Candle(
                symbol=c.symbol,
                timeframe=c.timeframe,
                timestamp=ts,
                open=round(c.open, decimals),
                high=round(c.high, decimals),
                low=round(c.low, decimals),
                close=round(c.close, decimals),
                volume=c.volume,
            )
        )

    normalized.sort(key=lambda c: c.timestamp)
    return normalized
