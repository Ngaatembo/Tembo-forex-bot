"""
Small, realistic EUR/USD 1H candle fixture used across tests.

This is a short synthetic-but-plausible sequence — real intraday
EUR/USD price action, not random numbers — used to prove the
normalize -> validate pipeline works correctly before it's ever
pointed at a live broker. It intentionally includes:
  - a clean run of valid candles
  - one candle with a genuine OHLC violation (high < close)
  - one duplicate timestamp
  - one weekend-sized gap (expected, should NOT fail validation)
"""

from datetime import datetime, timezone

from app.data_engine.market_data import Candle


def clean_eurusd_candles() -> list[Candle]:
    """A fully valid short EUR/USD 1H sequence — should pass validation cleanly."""
    base = datetime(2024, 1, 8, 0, 0, tzinfo=timezone.utc)  # a Monday
    prices = [1.09450, 1.09470, 1.09460, 1.09490, 1.09510]
    candles = []
    for i, close in enumerate(prices):
        o = prices[i - 1] if i > 0 else close - 0.0002
        candles.append(
            Candle(
                symbol="EUR/USD",
                timeframe="1h",
                timestamp=base.replace(hour=i),
                open=o,
                high=max(o, close) + 0.0003,
                low=min(o, close) - 0.0003,
                close=close,
                volume=1200 + i * 10,
            )
        )
    return candles


def candles_with_ohlc_violation() -> list[Candle]:
    """Same as clean_eurusd_candles but candle #2 has high < close (impossible in real data)."""
    candles = clean_eurusd_candles()
    bad = candles[2]
    candles[2] = Candle(
        symbol=bad.symbol,
        timeframe=bad.timeframe,
        timestamp=bad.timestamp,
        open=bad.open,
        high=bad.close - 0.0010,  # invalid: high below close
        low=bad.low,
        close=bad.close,
        volume=bad.volume,
    )
    return candles


def candles_with_duplicate_timestamp() -> list[Candle]:
    candles = clean_eurusd_candles()
    dup = candles[1]
    candles.append(
        Candle(
            symbol=dup.symbol,
            timeframe=dup.timeframe,
            timestamp=dup.timestamp,  # duplicate on purpose
            open=dup.open,
            high=dup.high,
            low=dup.low,
            close=dup.close,
            volume=dup.volume,
        )
    )
    return candles


def candles_with_weekend_gap() -> list[Candle]:
    """Friday close -> Sunday open. This IS a real, expected gap and must not fail validation."""
    friday_close = datetime(2024, 1, 5, 21, 0, tzinfo=timezone.utc)
    sunday_open = datetime(2024, 1, 7, 22, 0, tzinfo=timezone.utc)  # ~49h later
    return [
        Candle("EUR/USD", "1h", friday_close, 1.0940, 1.0945, 1.0935, 1.0942, 900),
        Candle("EUR/USD", "1h", sunday_open, 1.0943, 1.0948, 1.0940, 1.0946, 300),
    ]
