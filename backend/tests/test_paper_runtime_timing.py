from datetime import datetime, timedelta, timezone

from app.data_engine.market_data import Candle
from app.paper_trading.runtime import _completed_candles


NOW = datetime(2026, 9, 26, 12, 30, tzinfo=timezone.utc)


def candle(timestamp):
    return Candle(
        symbol="EUR/USD",
        timeframe="h1",
        timestamp=timestamp,
        open=1.1,
        high=1.2,
        low=1.0,
        close=1.15,
        volume=100.0,
    )


def test_completed_candles_excludes_forming_h1_bar():
    closed = candle(NOW - timedelta(hours=1, minutes=1))
    forming = candle(NOW - timedelta(minutes=30))

    result = _completed_candles([closed, forming], "h1", NOW)

    assert [item.timestamp for item in result] == [closed.timestamp]


def test_completed_candles_includes_bar_exactly_at_close_boundary():
    boundary = candle(NOW - timedelta(hours=1))

    result = _completed_candles([boundary], "h1", NOW)

    assert result == [boundary]


def test_completed_candles_uses_timeframe_delta():
    m15_closed = candle(NOW - timedelta(minutes=15))
    m15_forming = candle(NOW - timedelta(minutes=14))

    result = _completed_candles([m15_closed, m15_forming], "m15", NOW)

    assert [item.timestamp for item in result] == [m15_closed.timestamp]
