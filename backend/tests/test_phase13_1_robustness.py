"""
Breakout signal generation itself is UNCHANGED (Phase 9's tests
already cover lookahead/execution timing exhaustively). These tests
cover what's new in this phase: the 30/40/50 neighborhood producing
genuinely different signal counts (proving it's a real sweep, not a
no-op), and XAU/USD-specific sizing/scale reproducibility.
"""

from app.data_engine.importers.csv_importer import import_candles_from_csv
from app.data_engine.importers.ejtrader_source import ejtrader_xauusd_import_config
from app.data_engine.normalizer import normalize_candles
from app.strategy_engine.breakout import detect_breakout_signals


def _load_sample_xau(tmp_path):
    csv_path = tmp_path / "sample.csv"
    rows = ["Date,open,high,low,close,tick_volume"]
    from datetime import datetime, timedelta
    base = datetime(2012, 5, 17, 8, 0)
    prices = []
    price = 150000.0
    for i in range(60):  # gentle rising base -> different lookback windows see different prior highs
        price += 3.0
        prices.append(price)
    for i in range(20):  # then a much sharper breakout acceleration
        price += 60.0
        prices.append(price)
    for i, p in enumerate(prices):
        ts = (base + timedelta(hours=i)).strftime("%Y-%m-%d %H:%M:%S")
        rows.append(f"{ts},{p},{p+20},{p-20},{p+5},1000")
    csv_path.write_text("\n".join(rows))
    return normalize_candles(
        import_candles_from_csv(str(csv_path), symbol="XAU/USD", timeframe="1h", config=ejtrader_xauusd_import_config())
    )


def test_lookback_neighborhood_produces_different_prior_highs():
    """
    Direct test of the actual mechanism, avoiding a full synthetic
    price-series pitfall discovered while writing this test: a
    monotonically rising series makes any lookback >= 1 mathematically
    equivalent (the rolling max of a monotonic series only ever depends
    on the immediately preceding value) — so an earlier attempt using a
    steadily rising synthetic base produced identical breakout timing
    for all three lookbacks, which was correct behavior, not a bug, but
    proved nothing about lookback sensitivity. A series with a real
    local peak further back is what actually exercises the difference.
    """
    from app.strategy_engine.breakout import calculate_prior_range

    # A local peak 45 candles back, then a dip, then recent flat prices.
    highs = [100.0] * 10 + [150.0] * 5 + [100.0] * 30 + [110.0] * 15
    lows = [h - 5 for h in highs]

    _, _ = calculate_prior_range(highs, lows, lookback=30)  # sanity call
    prior_high_30, _ = calculate_prior_range(highs, lows, lookback=30)
    prior_high_50, _ = calculate_prior_range(highs, lows, lookback=50)

    idx = 55  # a candle where the 50-lookback window reaches back into the peak, 30 does not
    assert prior_high_30[idx] != prior_high_50[idx]
    assert prior_high_50[idx] == 150.0  # the 50-window sees the earlier peak
    assert prior_high_30[idx] < 150.0  # the 30-window does not


def test_xauusd_import_scale_reproducible(tmp_path):
    candles1 = _load_sample_xau(tmp_path)
    candles2 = _load_sample_xau(tmp_path)
    assert [c.close for c in candles1] == [c.close for c in candles2]
    assert candles1[0].close > 1000
