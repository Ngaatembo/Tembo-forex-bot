"""
Data quality audit — reports on a candle dataset before it's trusted
for backtesting. Distinct from validator.py's pass/fail check: this
produces a descriptive summary for human review (per Phase 4.5 spec
section 5), and it explicitly does NOT auto-repair anything.
"""

from dataclasses import dataclass, field

from app.data_engine.market_data import Candle
from app.data_engine.validator import ValidationReport, validate_candles


@dataclass
class DataQualityAudit:
    total_candles: int
    earliest_timestamp: str
    latest_timestamp: str
    timeframe: str
    symbol: str
    validation_report: ValidationReport


def audit_dataset(candles: list[Candle], *, symbol: str, timeframe: str) -> DataQualityAudit:
    if not candles:
        raise ValueError("Cannot audit an empty dataset.")

    # validate_candles() already excludes normal weekend market closures
    # from unexpected_gaps (see validator.py) — so every entry that DOES
    # show up there is a genuine anomaly worth a human looking at, not
    # a false alarm from Friday-close-to-Sunday-open.
    report = validate_candles(candles, timeframe=timeframe)

    return DataQualityAudit(
        total_candles=len(candles),
        earliest_timestamp=candles[0].timestamp.isoformat(),
        latest_timestamp=candles[-1].timestamp.isoformat(),
        timeframe=timeframe,
        symbol=symbol,
        validation_report=report,
    )


def format_audit_report(audit: DataQualityAudit) -> str:
    r = audit.validation_report
    lines = [
        f"Data Quality Audit — {audit.symbol} {audit.timeframe}",
        f"  Total candles:        {audit.total_candles}",
        f"  Earliest timestamp:   {audit.earliest_timestamp}",
        f"  Latest timestamp:     {audit.latest_timestamp}",
        f"  OHLC violations:      {len(r.ohlc_violations)}",
        f"  Zero/negative prices: {len(r.negative_or_zero_price)}",
        f"  Duplicate timestamps: {len(r.duplicate_timestamps)}",
        f"  Unexpected gaps:      {len(r.unexpected_gaps)} (weekend closures excluded automatically)",
        f"  Overall clean:        {r.is_clean}",
    ]
    if r.unexpected_gaps:
        lines.append("  Gap details (first 10):")
        for g in r.unexpected_gaps[:10]:
            lines.append(f"    - {g}")
    return "\n".join(lines)
