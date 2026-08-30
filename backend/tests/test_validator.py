from app.data_engine.normalizer import normalize_candles
from app.data_engine.validator import validate_candles
from tests.fixtures.eurusd_candles import (
    candles_with_ohlc_violation,
    candles_with_weekend_gap,
    clean_eurusd_candles,
)


def test_clean_candles_pass_validation():
    candles = normalize_candles(clean_eurusd_candles())
    report = validate_candles(candles, timeframe="1h")
    assert report.is_clean
    assert report.total_candles == 5


def test_ohlc_violation_is_caught():
    candles = normalize_candles(candles_with_ohlc_violation())
    report = validate_candles(candles, timeframe="1h")
    assert not report.is_clean
    assert len(report.ohlc_violations) == 1


def test_weekend_gap_does_not_fail_validation():
    """Critical: a Fri-close -> Sun-open gap is normal forex market behavior,
    not corrupted data, and must not block storage."""
    candles = normalize_candles(candles_with_weekend_gap())
    report = validate_candles(candles, timeframe="1h")
    assert report.is_clean  # gaps alone never make is_clean False
    assert len(report.unexpected_gaps) == 0  # ~49h is within the weekend allowance


def test_unreasonable_gap_is_flagged():
    candles = normalize_candles(clean_eurusd_candles())
    # Manually blow out one timestamp far beyond any weekend
    from datetime import timedelta
    candles[3] = candles[3].__class__(
        symbol=candles[3].symbol, timeframe=candles[3].timeframe,
        timestamp=candles[2].timestamp + timedelta(days=10),
        open=candles[3].open, high=candles[3].high, low=candles[3].low,
        close=candles[3].close, volume=candles[3].volume,
    )
    candles.sort(key=lambda c: c.timestamp)
    report = validate_candles(candles, timeframe="1h")
    assert len(report.unexpected_gaps) == 1
