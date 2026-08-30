from datetime import datetime, timezone

from app.data_engine.market_data import Candle
from app.data_engine.normalizer import normalize_candles
from tests.fixtures.eurusd_candles import candles_with_duplicate_timestamp, clean_eurusd_candles


def test_normalize_sorts_by_timestamp():
    candles = list(reversed(clean_eurusd_candles()))
    result = normalize_candles(candles)
    timestamps = [c.timestamp for c in result]
    assert timestamps == sorted(timestamps)


def test_normalize_deduplicates_timestamps():
    candles = candles_with_duplicate_timestamp()
    assert len(candles) == 6  # 5 clean + 1 duplicate
    result = normalize_candles(candles)
    assert len(result) == 5  # duplicate removed


def test_normalize_forces_utc():
    naive = Candle(
        symbol="EUR/USD",
        timeframe="1h",
        timestamp=datetime(2024, 1, 8, 12, 0),  # no tzinfo
        open=1.09, high=1.10, low=1.08, close=1.095, volume=100,
    )
    result = normalize_candles([naive])
    assert result[0].timestamp.tzinfo == timezone.utc


def test_normalize_rounds_price_noise():
    noisy = Candle(
        symbol="EUR/USD", timeframe="1h",
        timestamp=datetime(2024, 1, 8, 12, 0, tzinfo=timezone.utc),
        open=1.100000000000002, high=1.1005, low=1.0995, close=1.10001, volume=100,
    )
    result = normalize_candles([noisy], decimals=5)
    assert result[0].open == 1.1
