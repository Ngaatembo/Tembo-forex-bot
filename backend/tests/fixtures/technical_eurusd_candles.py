"""
A realistic-LOOKING but entirely SYNTHETIC 50-candle EUR/USD 1H
sequence, used only as a deterministic test fixture for the technical
engine. This is not real market data and must never be presented as
such — it exists purely so SMA10/SMA50 tests have a plausible,
non-trivial price series to compute against.
"""

from datetime import datetime, timedelta, timezone

from app.data_engine.market_data import Candle


def synthetic_eurusd_50_candles() -> list[Candle]:
    base_time = datetime(2024, 1, 8, 0, 0, tzinfo=timezone.utc)
    base_price = 1.09500

    # Small deterministic pseudo-random walk (fixed seed pattern, not
    # numpy.random, so results never vary between test runs/environments)
    deltas = [
        0.0005, -0.0003, 0.0002, 0.0004, -0.0006, 0.0001, 0.0003, -0.0002,
        0.0005, -0.0004, 0.0002, 0.0001, -0.0003, 0.0006, -0.0001, 0.0002,
        -0.0005, 0.0004, 0.0003, -0.0002, 0.0001, -0.0004, 0.0005, 0.0002,
        -0.0001, 0.0003, -0.0006, 0.0004, 0.0001, -0.0002, 0.0005, -0.0003,
        0.0002, 0.0004, -0.0001, 0.0003, -0.0005, 0.0002, 0.0001, -0.0004,
        0.0006, -0.0002, 0.0003, -0.0001, 0.0004, -0.0003, 0.0002, 0.0005,
        -0.0004, 0.0001,
    ]

    candles = []
    close = base_price
    for i, delta in enumerate(deltas):
        open_ = close
        close = round(close + delta, 5)
        high = round(max(open_, close) + 0.0002, 5)
        low = round(min(open_, close) - 0.0002, 5)
        candles.append(
            Candle(
                symbol="EUR/USD",
                timeframe="1h",
                timestamp=base_time + timedelta(hours=i),
                open=open_,
                high=high,
                low=low,
                close=close,
                volume=1000 + i,
            )
        )
    return candles
