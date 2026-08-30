"""
SYNTHETIC TEST DATA — NOT REAL MARKET DATA.

A deliberately engineered EUR/USD-shaped 1H candle sequence designed
to produce known, well-separated SMA10/50 crossovers: a flat opening
period (no signal), a sustained rise (triggers a BUY), a flat plateau,
a sustained fall (triggers a SELL/reversal), and a final flat period.
Used only to give the backtesting engine tests a realistic-shaped,
fully deterministic price path with predictable crossover behavior —
never to be presented as, or confused with, real market performance.
"""

from datetime import datetime, timedelta, timezone

from app.data_engine.market_data import Candle


def trending_candles(
    flat1: int = 60, rise: int = 20, flat2: int = 20, fall: int = 20, flat3: int = 20
) -> list[Candle]:
    base_time = datetime(2024, 1, 8, 0, 0, tzinfo=timezone.utc)
    price = 1.09000
    candles: list[Candle] = []
    hour = 0

    def add_candle(delta: float):
        nonlocal price, hour
        open_ = price
        price = round(price + delta, 5)
        high = round(max(open_, price) + 0.0001, 5)
        low = round(min(open_, price) - 0.0001, 5)
        candles.append(
            Candle(
                symbol="EUR/USD", timeframe="1h",
                timestamp=base_time + timedelta(hours=hour),
                open=open_, high=high, low=low, close=price, volume=1000,
            )
        )
        hour += 1

    # Flat/no-trend: tiny alternating wobble, average delta ~0
    for i in range(flat1):
        add_candle(0.0002 if i % 2 == 0 else -0.0002)
    # Sustained rise: fast MA (SMA10) pulls ahead of slow MA (SMA50) -> BUY
    for _ in range(rise):
        add_candle(0.0008)
    # Flat plateau at the new high level
    for i in range(flat2):
        add_candle(0.0001 if i % 2 == 0 else -0.0001)
    # Sustained fall: fast MA drops below slow MA -> SELL (closes long, opens short)
    for _ in range(fall):
        add_candle(-0.0008)
    # Flat/no-trend tail
    for i in range(flat3):
        add_candle(0.0002 if i % 2 == 0 else -0.0002)

    return candles


def extreme_future_candles(count: int = 10, start_hour: int = 1000) -> list[Candle]:
    """An absurd, obviously-fake price spike used only to prove that
    appending it after a backtest's cutoff can't change results computed
    before the cutoff (the lookahead-bias regression test)."""
    base_time = datetime(2024, 1, 8, 0, 0, tzinfo=timezone.utc) + timedelta(hours=start_hour)
    candles = []
    price = 5.00000
    for i in range(count):
        candles.append(
            Candle(
                symbol="EUR/USD", timeframe="1h",
                timestamp=base_time + timedelta(hours=i),
                open=price, high=price + 0.5, low=price - 0.5, close=price + (i * 0.3),
                volume=999999,
            )
        )
        price += 0.3
    return candles
