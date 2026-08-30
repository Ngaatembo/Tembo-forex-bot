"""
H1/breakout/momentum signal generators are UNCHANGED in this phase —
their lookahead/execution-timing/last-candle tests already cover that
logic exhaustively; re-testing it here would be pure duplication.
These tests cover what's actually new: importing a NON-EUR/USD pair
through the existing generic importer, and dataset reproducibility
for a new instrument.
"""

from app.data_engine.importers.csv_importer import import_candles_from_csv
from app.data_engine.importers.ejtrader_source import ejtrader_import_config
from app.data_engine.normalizer import normalize_candles
from app.data_engine.validator import validate_candles
from app.research.dataset_version import compute_file_sha256


def test_generic_importer_works_for_gbpusd_not_just_eurusd(tmp_path):
    csv_path = tmp_path / "sample.csv"
    csv_path.write_text(
        "Date,open,high,low,close,tick_volume\n"
        "2012-11-16 05:00:00,158611.0,158618.0,158572.0,158599.0,1032\n"
        "2012-11-16 06:00:00,158599.0,158650.0,158550.0,158600.0,1100\n"
    )
    candles = import_candles_from_csv(
        str(csv_path), symbol="GBP/USD", timeframe="1h", config=ejtrader_import_config(),
    )
    assert len(candles) == 2
    assert candles[0].symbol == "GBP/USD"
    assert round(candles[0].open, 5) == 1.58611


def test_xauusd_requires_its_own_price_scale_not_the_forex_one():
    """
    Regression test for a real bug found in Phase 13: this source scales
    XAU/USD to 2 decimals (gold's real quoting convention), NOT the
    5-decimal forex convention. Verified against real history: gold
    traded ~$1547-1550/oz on 2012-05-17. Using the forex config here
    would silently produce 1.54759 instead of 1547.59 — 1000x wrong.
    """
    from app.data_engine.importers.ejtrader_source import ejtrader_xauusd_import_config

    csv_path_content = (
        "Date,open,high,low,close,tick_volume\n"
        "2012-05-17 08:00:00,154759.0,155384.0,154740.0,155295.0,4418\n"
    )
    import tempfile, os
    fd, path = tempfile.mkstemp(suffix=".csv")
    with os.fdopen(fd, "w") as f:
        f.write(csv_path_content)

    wrong = import_candles_from_csv(path, symbol="XAU/USD", timeframe="1h", config=ejtrader_import_config())
    correct = import_candles_from_csv(path, symbol="XAU/USD", timeframe="1h", config=ejtrader_xauusd_import_config())
    os.remove(path)

    assert round(wrong[0].open, 5) == 1.54759  # what the WRONG (forex) config produces
    assert round(correct[0].open, 2) == 1547.59  # the actual real gold price


def test_imported_gbpusd_data_passes_phase1_validation(tmp_path):
    csv_path = tmp_path / "sample.csv"
    csv_path.write_text(
        "Date,open,high,low,close,tick_volume\n"
        "2012-11-16 05:00:00,158611.0,158618.0,158572.0,158599.0,1032\n"
        "2012-11-16 06:00:00,158599.0,158650.0,158550.0,158600.0,1100\n"
        "2012-11-16 07:00:00,158600.0,158700.0,158580.0,158650.0,1050\n"
    )
    candles = normalize_candles(
        import_candles_from_csv(str(csv_path), symbol="GBP/USD", timeframe="1h", config=ejtrader_import_config())
    )
    report = validate_candles(candles, timeframe="1h")
    assert report.is_clean


def test_dataset_hash_reproducible_for_new_instrument(tmp_path):
    csv_path = tmp_path / "sample.csv"
    csv_path.write_text("Date,open,high,low,close,tick_volume\n2012-11-16 05:00:00,158611.0,158618.0,158572.0,158599.0,1032\n")
    hash1 = compute_file_sha256(str(csv_path))
    hash2 = compute_file_sha256(str(csv_path))
    assert hash1 == hash2
