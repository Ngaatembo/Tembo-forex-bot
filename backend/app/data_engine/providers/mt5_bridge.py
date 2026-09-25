"""
MetaTrader 5 bridge market-data provider.

Render cannot run the MetaTrader 5 desktop terminal itself. This adapter
talks to a small authenticated HTTP bridge running beside an MT5 terminal
on Windows. The bridge exposes read-only price/candle operations for the
first integration phase.

Trading/order endpoints are deliberately NOT implemented here yet.
Live execution remains disabled.
"""

from datetime import datetime, timezone

import httpx

from app.core.config import get_settings
from app.data_engine.market_data import Candle, InstrumentMetadata, MarketDataProvider


_SYMBOL_MAP = {
    "EUR/USD": "EURUSD",
    "GBP/USD": "GBPUSD",
    "USD/JPY": "USDJPY",
    "XAU/USD": "XAUUSD",
}

_TIMEFRAME_MAP = {
    "m5": "M5",
    "m15": "M15",
    "h1": "H1",
    "h4": "H4",
    "d1": "D1",
}

_PIP_SIZES = {
    "EUR/USD": 0.0001,
    "GBP/USD": 0.0001,
    "USD/JPY": 0.01,
    "XAU/USD": 0.01,
}


class MT5BridgeProvider(MarketDataProvider):
    def __init__(self) -> None:
        settings = get_settings()
        if not settings.mt5_bridge_url:
            raise ValueError("MT5_BRIDGE_URL is required when MARKET_DATA_PROVIDER=mt5_bridge.")
        if not settings.mt5_bridge_token:
            raise ValueError("MT5_BRIDGE_TOKEN is required when MARKET_DATA_PROVIDER=mt5_bridge.")

        self._base_url = settings.mt5_bridge_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {settings.mt5_bridge_token}"}
        self._client = httpx.AsyncClient(headers=self._headers, timeout=15.0)

    def _symbol(self, symbol: str) -> str:
        try:
            return _SYMBOL_MAP[symbol]
        except KeyError as exc:
            raise ValueError(f"Unsupported MT5 bridge symbol: {symbol}") from exc

    def _timeframe(self, timeframe: str) -> str:
        try:
            return _TIMEFRAME_MAP[timeframe]
        except KeyError as exc:
            raise ValueError(f"Unsupported MT5 bridge timeframe: {timeframe}") from exc

    async def get_current_price(self, symbol: str) -> float:
        response = await self._client.get(
            f"{self._base_url}/price",
            params={"symbol": self._symbol(symbol)},
        )
        response.raise_for_status()
        body = response.json()
        return float(body["mid"])

    async def get_candles(self, symbol: str, timeframe: str, limit: int = 500) -> list[Candle]:
        response = await self._client.get(
            f"{self._base_url}/candles",
            params={
                "symbol": self._symbol(symbol),
                "timeframe": self._timeframe(timeframe),
                "limit": min(limit, 5000),
            },
        )
        response.raise_for_status()
        return self._parse_candles(response.json()["candles"], symbol, timeframe)

    async def get_historical_data(
        self, symbol: str, timeframe: str, start: datetime, end: datetime
    ) -> list[Candle]:
        candles = await self.get_candles(symbol, timeframe, limit=5000)
        start_utc = start.astimezone(timezone.utc)
        end_utc = end.astimezone(timezone.utc)
        return [c for c in candles if start_utc <= c.timestamp <= end_utc]

    async def get_instrument_metadata(self, symbol: str) -> InstrumentMetadata:
        if symbol not in _SYMBOL_MAP:
            raise ValueError(f"Unsupported MT5 bridge symbol: {symbol}")
        return InstrumentMetadata(
            symbol=symbol,
            display_name=symbol,
            pip_size=_PIP_SIZES.get(symbol, 0.0001),
        )

    @staticmethod
    def _parse_candles(values: list[dict], symbol: str, timeframe: str) -> list[Candle]:
        candles: list[Candle] = []
        for value in values:
            timestamp = datetime.fromtimestamp(int(value["time"]), tz=timezone.utc)
            candles.append(
                Candle(
                    symbol=symbol,
                    timeframe=timeframe,
                    timestamp=timestamp,
                    open=float(value["open"]),
                    high=float(value["high"]),
                    low=float(value["low"]),
                    close=float(value["close"]),
                    volume=float(value.get("tick_volume", 0)),
                )
            )
        return sorted(candles, key=lambda candle: candle.timestamp)
