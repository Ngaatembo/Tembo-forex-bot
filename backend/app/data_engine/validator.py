"""
Data quality validation for candle series.

This module never silently drops or "fixes" bad data — it reports
problems so the caller (the ingestion script, in Phase 1) can decide
what to do. Silently patching bad candles is how a backtest ends up
quietly trained on corrupted data.
"""

from dataclasses import dataclass, field
from datetime import timedelta

from app.data_engine.market_data import Candle

_TIMEFRAME_DELTAS = {
    "1m": timedelta(minutes=1),
    "5m": timedelta(minutes=5),
    "15m": timedelta(minutes=15),
    "1h": timedelta(hours=1),
    "4h": timedelta(hours=4),
    "1d": timedelta(days=1),
}


@dataclass
class ValidationReport:
    total_candles: int
    ohlc_violations: list[str] = field(default_factory=list)
    negative_or_zero_price: list[str] = field(default_factory=list)
    unexpected_gaps: list[str] = field(default_factory=list)
    duplicate_timestamps: list[str] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return not (
            self.ohlc_violations
            or self.negative_or_zero_price
            or self.duplicate_timestamps
        )
        # Note: gaps are reported but deliberately NOT part of is_clean —
        # forex markets close every weekend, so gaps are often expected,
        # not corruption. See validate_candles() below.


def validate_candles(
    candles: list[Candle], timeframe: str, max_reasonable_gap_multiplier: int = 4
) -> ValidationReport:
    """
    Assumes `candles` is already normalized (sorted, UTC, deduped) —
    run normalize_candles() first. Checks, in order:

    1. OHLC sanity: high must be >= open/close/low; low must be <=
       open/close/high. A violation here means the data itself is
       broken, not that the market did something unusual.
    2. No negative or zero prices — a zero close is almost always a
       data outage, not a real quote.
    3. Gaps larger than expected for the timeframe. Weekend gaps in
       forex are normal and expected (~48h from Friday close to Sunday
       open) — this flags gaps beyond a generous multiple of the
       candle interval, which is what actually indicates missing data
       versus market closure.
    4. Duplicate timestamps (should be impossible after normalization,
       checked here anyway as a safety net for callers who skip it).
    """
    report = ValidationReport(total_candles=len(candles))
    delta = _TIMEFRAME_DELTAS[timeframe]
    seen: set = set()

    for i, c in enumerate(candles):
        if c.high < max(c.open, c.close, c.low) or c.low > min(c.open, c.close, c.high):
            report.ohlc_violations.append(
                f"index {i} ({c.timestamp.isoformat()}): O={c.open} H={c.high} L={c.low} C={c.close}"
            )

        if c.open <= 0 or c.high <= 0 or c.low <= 0 or c.close <= 0:
            report.negative_or_zero_price.append(f"index {i} ({c.timestamp.isoformat()})")

        if c.timestamp in seen:
            report.duplicate_timestamps.append(c.timestamp.isoformat())
        seen.add(c.timestamp)

        if i > 0:
            gap = c.timestamp - candles[i - 1].timestamp
            # Weekend closures produce a large but legitimate gap; only
            # flag something bigger than that as suspicious.
            weekend_allowance = timedelta(hours=50)
            max_allowed = max(delta * max_reasonable_gap_multiplier, weekend_allowance)
            if gap > max_allowed:
                report.unexpected_gaps.append(
                    f"{candles[i-1].timestamp.isoformat()} -> {c.timestamp.isoformat()} "
                    f"(gap: {gap})"
                )

    return report
