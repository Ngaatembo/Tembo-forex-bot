"""
SYNTHETIC TEST DATA — NOT REAL MARKET DATA.

Hand-engineered candle sequences built purely to exercise regime
classification logic against known, intended shapes. None of these
represent real market behavior — they exist only to verify that
classify_regime() does what its documented rules say it does.
"""

from datetime import datetime, timedelta, timezone

from app.data_engine.market_data import Candle

BASE = datetime(2024, 1, 8, 0, 0, tzinfo=timezone.utc)


def _build(deltas: list[float], wick: float = 0.0001, base_price: float = 1.09000) -> list[Candle]:
    candles = []
    price = base_price
    for i, delta in enumerate(deltas):
        open_ = price
        price = round(price + delta, 5)
        high = round(max(open_, price) + wick, 5)
        low = round(min(open_, price) - wick, 5)
        candles.append(
            Candle(
                symbol="EUR/USD", timeframe="1h", timestamp=BASE + timedelta(hours=i),
                open=open_, high=high, low=low, close=price, volume=1000,
            )
        )
    return candles


def steadily_rising_market(n: int = 80) -> list[Candle]:
    """A clean, steady uptrend with small consistent wicks (low, stable volatility)."""
    return _build([0.0006] * n, wick=0.0001)


def steadily_falling_market(n: int = 80) -> list[Candle]:
    return _build([-0.0006] * n, wick=0.0001)


def sideways_ranging_market(n: int = 80) -> list[Candle]:
    """Oscillates with no net direction and moderate (not extreme) wicks."""
    deltas = [0.0003 if i % 2 == 0 else -0.0003 for i in range(n)]
    return _build(deltas, wick=0.0002)


def high_volatility_market(n: int = 80) -> list[Candle]:
    """Large, erratic swings each candle — wide wicks driving ATR% well above threshold."""
    deltas = [0.0030 if i % 2 == 0 else -0.0025 for i in range(n)]
    return _build(deltas, wick=0.0025)


def insufficient_data_market(n: int = 20) -> list[Candle]:
    """Fewer candles than any indicator's warm-up period — everything should be None/UNKNOWN."""
    return _build([0.0004] * n, wick=0.0001)
