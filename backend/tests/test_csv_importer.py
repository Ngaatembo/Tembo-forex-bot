"""
Tests the historical-data import path: raw CSV -> importer -> Phase 1
normalize_candles -> Phase 1 validate_candles -> Phase 4 backtest.

Uses a real 20-row excerpt of the actual ejtraderLabs/historical-data
EUR/USD dataset (tests/fixtures/sample_data/sample_ejtrader_eurusd_h1.csv)
— genuine historical prices, just a small slice, used only so these
tests don't need network access to re-download the full ~57k-row file.
"""

import pytest

from app.data_engine.importers.csv_importer import CSVImportConfig, import_candles_from_csv
from app.data_engine.importers.ejtrader_source import ejtrader_import_config, import_ejtrader_eurusd_h1
from app.data_engine.normalizer import normalize_candles
from app.data_engine.validator import validate_candles
from app.backtesting.config import BacktestConfig
from app.backtesting.engine import run_backtest

SAMPLE_CSV = "tests/fixtures/sample_data/sample_ejtrader_eurusd_h1.csv"


def test_real_format_parses_correctly():
    """Test 1 — known real values from the actual dataset."""
    candles = import_ejtrader_eurusd_h1(SAMPLE_CSV)

    assert len(candles) == 20
    first = candles[0]
    assert first.symbol == "EUR/USD"
    assert first.timeframe == "1h"
    # 127801.00000000001 / 100000 -> 1.27801 (rounding handles the float noise)
    assert round(first.open, 5) == 1.27801
    assert round(first.close, 5) == 1.27810


def test_invalid_rows_are_rejected(tmp_path):
    """Test 2 — a non-numeric price value must fail loudly, not silently become 0/NaN."""
    bad_csv = tmp_path / "bad.csv"
    bad_csv.write_text(
        "Date,open,high,low,close,tick_volume\n"
        "2024-01-01 00:00:00,NOT_A_NUMBER,1.10,1.09,1.095,100\n"
    )
    with pytest.raises(ValueError):
        import_ejtrader_eurusd_h1(str(bad_csv))


def test_missing_required_column_is_rejected(tmp_path):
    csv_path = tmp_path / "missing_col.csv"
    csv_path.write_text("Date,open,high,low,tick_volume\n2024-01-01 00:00:00,1.10,1.11,1.09,100\n")
    config = CSVImportConfig(
        timestamp_column="Date", open_column="open", high_column="high",
        low_column="low", close_column="close",  # "close" doesn't exist in this file
    )
    with pytest.raises(ValueError, match="missing"):
        import_candles_from_csv(str(csv_path), symbol="EUR/USD", timeframe="1h", config=config)


def test_duplicate_timestamps_are_preserved_by_importer_and_caught_by_validator(tmp_path):
    """
    Test 3 — the importer itself does NOT deduplicate (that's the
    normalizer's job, per the architectural boundary); this proves
    the duplicate survives import and is then actually caught by
    Phase 1's validator, not a new/duplicate check.
    """
    csv_path = tmp_path / "dup.csv"
    csv_path.write_text(
        "Date,open,high,low,close,tick_volume\n"
        "2024-01-01 00:00:00,110000,110500,109500,110200,100\n"
        "2024-01-01 00:00:00,110200,110600,110000,110400,100\n"  # duplicate timestamp
        "2024-01-01 01:00:00,110400,110700,110100,110500,100\n",
    )
    config = ejtrader_import_config()
    candles = import_candles_from_csv(str(csv_path), symbol="EUR/USD", timeframe="1h", config=config)

    assert len(candles) == 3  # importer preserved the duplicate as-is

    report = validate_candles(candles, timeframe="1h")
    assert len(report.duplicate_timestamps) == 1  # Phase 1's own validator caught it


def test_out_of_order_csv_rows_are_sorted_by_normalizer(tmp_path):
    """Test 4 — chronological ordering is enforced by REUSING normalize_candles, not a new sort."""
    csv_path = tmp_path / "unordered.csv"
    csv_path.write_text(
        "Date,open,high,low,close,tick_volume\n"
        "2024-01-01 02:00:00,110400,110700,110100,110500,100\n"
        "2024-01-01 00:00:00,110000,110500,109500,110200,100\n"
        "2024-01-01 01:00:00,110200,110600,110000,110400,100\n",
    )
    config = ejtrader_import_config()
    raw_candles = import_candles_from_csv(str(csv_path), symbol="EUR/USD", timeframe="1h", config=config)
    assert raw_candles[0].timestamp > raw_candles[1].timestamp  # confirms the file WAS out of order

    normalized = normalize_candles(raw_candles)
    timestamps = [c.timestamp for c in normalized]
    assert timestamps == sorted(timestamps)


def test_phase1_validation_is_reused_and_reports_clean_real_data():
    """Test 5 — real weekday market data should pass Phase 1 validation cleanly."""
    candles = import_ejtrader_eurusd_h1(SAMPLE_CSV)
    normalized = normalize_candles(candles)
    report = validate_candles(normalized, timeframe="1h")
    assert report.is_clean


def test_import_is_deterministic():
    """Test 6."""
    first = import_ejtrader_eurusd_h1(SAMPLE_CSV)
    second = import_ejtrader_eurusd_h1(SAMPLE_CSV)
    assert first == second


def test_imported_candles_flow_through_the_real_backtest_engine():
    """Test 7 — proves canonical candles from a real-data import are
    accepted by the unmodified Phase 4 engine with no adapter/shim
    needed. Only 20 candles (fewer than the 50-candle SMA50 warm-up),
    so zero trades is the CORRECT outcome here — this test is about
    wiring compatibility, not about producing a real result."""
    candles = import_ejtrader_eurusd_h1(SAMPLE_CSV)
    normalized = normalize_candles(candles)
    report = validate_candles(normalized, timeframe="1h")
    assert report.is_clean

    result = run_backtest(normalized, BacktestConfig())
    assert result.summary.trade_count == 0  # correct given <50 candles, not a failure


def test_future_candles_appended_to_real_data_do_not_change_earlier_equity(tmp_path):
    """Test 10 — the lookahead-bias guarantee holds for real-data-shaped input too."""
    from datetime import datetime, timedelta, timezone
    from app.data_engine.market_data import Candle

    candles = normalize_candles(import_ejtrader_eurusd_h1(SAMPLE_CSV))
    config = BacktestConfig()

    baseline = run_backtest(candles, config)

    future = [
        Candle(
            symbol="EUR/USD", timeframe="1h",
            timestamp=candles[-1].timestamp + timedelta(hours=i + 1),
            open=5.0, high=5.5, low=4.5, close=5.0 + i, volume=999999,
        )
        for i in range(5)
    ]
    extended = run_backtest(candles + future, config)

    assert baseline.equity_curve == extended.equity_curve[: len(baseline.equity_curve)]
