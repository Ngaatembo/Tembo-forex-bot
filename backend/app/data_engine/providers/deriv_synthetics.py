"""Deriv synthetic-index market-data adapter.

This adapter is deliberately read-only. It uses Deriv's public WebSocket
market-data API for active symbols, spot ticks, and historical candles.
No account authentication, proposal, buy, sell, or real-money execution is
performed here.
"""

from datetime import datetime, timezone
import time

import websockets

from app.core.config import get_settings
from app.data_engine.market_data import Candle, InstrumentMetadata, MarketDataProvider

DERIV_PUBLIC_WS = "wss://api.derivws.com/trading/v1/options/ws/public"
SYNTHETIC_PREFIX = "SYNTH:"
_TIMEFRAME_GRANULARITY = {
    "m5": 300,
    "m15": 900,
    "h1": 3600,
    "h4": 14400,
    "d1": 86400,
}


class DerivSyntheticProviderError(Exception):
    pass


class UnsupportedSyntheticError(DerivSyntheticProviderError):
    pass


class UnsupportedTimeframeError(DerivSyntheticProviderError):
    pass


class MalformedResponseError(DerivSyntheticProviderError):
    pass


class DerivSyntheticProvider(MarketDataProvider):
    # Deriv's current public API rejects a "subscribe" field on one-off
    # ticks/ticks_history requests ("Input validation failed: subscribe"),
    # so requests below deliberately omit it, like the forex adapter.
    _symbols_cache: tuple[float, list[dict]] | None = None
    _symbols_ttl = 300.0
    _price_cache: dict[str, tuple[float, float]] = {}
    _price_ttl = 2.0
    _candles_cache: dict[tuple[str, str, int], tuple[float, list[Candle]]] = {}
    _candles_ttl = 20.0

    def __init__(self):
        settings = get_settings()
        self._ws_url = settings.deriv_public_ws_url or DERIV_PUBLIC_WS

    @staticmethod
    def is_synthetic_instrument(symbol: str) -> bool:
        return symbol.startswith(SYNTHETIC_PREFIX) and len(symbol) > len(SYNTHETIC_PREFIX)

    @staticmethod
    def provider_symbol(symbol: str) -> str:
        if not DerivSyntheticProvider.is_synthetic_instrument(symbol):
            raise UnsupportedSyntheticError(
                f"Expected a synthetic instrument in the {SYNTHETIC_PREFIX}<symbol> format."
            )
        return symbol[len(SYNTHETIC_PREFIX):]

    async def _request(self, payload: dict, expected_type: str) -> dict:
        try:
            async with websockets.connect(self._ws_url, open_timeout=15, close_timeout=5) as ws:
                await ws.send(__import__("json").dumps(payload))
                deadline = time.monotonic() + 20
                while time.monotonic() < deadline:
                    raw = await ws.recv()
                    response = __import__("json").loads(raw)
                    if response.get("error"):
                        error = response["error"]
                        raise DerivSyntheticProviderError(
                            f"Deriv API error {error.get('code')}: {error.get('message')}"
                        )
                    if response.get("msg_type") == expected_type:
                        return response
                raise DerivSyntheticProviderError(
                    f"Timed out waiting for Deriv {expected_type} response."
                )
        except DerivSyntheticProviderError:
            raise
        except Exception as exc:
            raise DerivSyntheticProviderError(
                f"Deriv public market-data connection failed: {exc}"
            ) from exc

    async def get_active_synthetics(self) -> list[dict]:
        cached = self._symbols_cache
        now = time.monotonic()
        if cached and now - cached[0] < self._symbols_ttl:
            return [dict(item) for item in cached[1]]

        response = await self._request(
            {"active_symbols": "brief", "req_id": 1},
            "active_symbols",
        )
        records = response.get("active_symbols")
        if not isinstance(records, list):
            raise MalformedResponseError("Deriv active_symbols response is missing a list.")

        synthetics = []
        for item in records:
            if not isinstance(item, dict):
                continue
            underlying = item.get("underlying_symbol")
            market = str(item.get("market", "")).lower()
            symbol_type = str(item.get("underlying_symbol_type", "")).lower()
            if not underlying or (
                "synthetic" not in market and "synthetic" not in symbol_type
            ):
                continue
            if item.get("is_trading_suspended"):
                continue
            synthetics.append(
                {
                    "symbol": f"{SYNTHETIC_PREFIX}{underlying}",
                    "underlying_symbol": underlying,
                    "display_name": item.get("underlying_symbol_name") or underlying,
                    "market": market,
                    "submarket": item.get("submarket"),
                    "subgroup": item.get("subgroup"),
                    "pip_size": float(item.get("pip_size") or 0),
                    "exchange_is_open": bool(item.get("exchange_is_open", 1)),
                }
            )

        synthetics.sort(key=lambda item: (str(item["display_name"]), item["underlying_symbol"]))
        self._symbols_cache = (time.monotonic(), synthetics)
        return [dict(item) for item in synthetics]

    async def _metadata(self, symbol: str) -> dict:
        provider_symbol = self.provider_symbol(symbol)
        for item in await self.get_active_synthetics():
            if item["underlying_symbol"] == provider_symbol:
                return item
        raise UnsupportedSyntheticError(
            f"Synthetic symbol {provider_symbol!r} is not currently active on Deriv."
        )

    async def get_current_price(self, symbol: str) -> float:
        provider_symbol = self.provider_symbol(symbol)
        await self._metadata(symbol)
        cached = self._price_cache.get(symbol)
        if cached and time.monotonic() - cached[0] < self._price_ttl:
            return cached[1]
        response = await self._request(
            {"ticks": provider_symbol, "req_id": 2},
            "tick",
        )
        try:
            price = float(response["tick"]["quote"])
        except (KeyError, TypeError, ValueError) as exc:
            raise MalformedResponseError("Deriv tick response did not contain a numeric quote.") from exc
        self._price_cache[symbol] = (time.monotonic(), price)
        return price

    @staticmethod
    def _granularity(timeframe: str) -> int:
        try:
            return _TIMEFRAME_GRANULARITY[timeframe.lower()]
        except KeyError as exc:
            raise UnsupportedTimeframeError(
                f"Timeframe {timeframe!r} is not supported. Allowed: {sorted(_TIMEFRAME_GRANULARITY)}."
            ) from exc

    async def get_candles(self, symbol: str, timeframe: str, limit: int = 500) -> list[Candle]:
        provider_symbol = self.provider_symbol(symbol)
        await self._metadata(symbol)
        granularity = self._granularity(timeframe)
        count = min(max(limit, 1), 5000)
        cache_key = (symbol, timeframe.lower(), count)
        cached = self._candles_cache.get(cache_key)
        if cached and time.monotonic() - cached[0] < self._candles_ttl:
            return list(cached[1])
        response = await self._request(
            {
                "ticks_history": provider_symbol,
                "end": "latest",
                "count": count,
                "style": "candles",
                "granularity": granularity,
                "req_id": 3,
            },
            "candles",
        )
        raw = response.get("candles")
        if not isinstance(raw, list):
            raise MalformedResponseError("Deriv candle response is missing a list.")

        parsed: list[Candle] = []
        try:
            for item in raw:
                timestamp = datetime.fromtimestamp(int(item["epoch"]), tz=timezone.utc)
                parsed.append(
                    Candle(
                        symbol=symbol,
                        timeframe=timeframe.lower(),
                        timestamp=timestamp,
                        open=float(item["open"]),
                        high=float(item["high"]),
                        low=float(item["low"]),
                        close=float(item["close"]),
                        volume=None,
                    )
                )
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise MalformedResponseError(f"Could not parse Deriv candles: {exc}") from exc

        parsed.sort(key=lambda candle: candle.timestamp)
        self._candles_cache[cache_key] = (time.monotonic(), parsed)
        return list(parsed)

    async def get_historical_data(
        self, symbol: str, timeframe: str, start: datetime, end: datetime
    ) -> list[Candle]:
        provider_symbol = self.provider_symbol(symbol)
        await self._metadata(symbol)
        granularity = self._granularity(timeframe)
        start_epoch = int(start.astimezone(timezone.utc).timestamp())
        end_epoch = int(end.astimezone(timezone.utc).timestamp())
        response = await self._request(
            {
                "ticks_history": provider_symbol,
                "start": start_epoch,
                "end": end_epoch,
                "style": "candles",
                "granularity": granularity,
                "req_id": 4,
            },
            "candles",
        )
        raw = response.get("candles")
        if not isinstance(raw, list):
            raise MalformedResponseError("Deriv historical candle response is missing a list.")

        parsed = []
        for item in raw:
            try:
                parsed.append(
                    Candle(
                        symbol=symbol,
                        timeframe=timeframe.lower(),
                        timestamp=datetime.fromtimestamp(int(item["epoch"]), tz=timezone.utc),
                        open=float(item["open"]),
                        high=float(item["high"]),
                        low=float(item["low"]),
                        close=float(item["close"]),
                        volume=None,
                    )
                )
            except (KeyError, TypeError, ValueError, OverflowError) as exc:
                raise MalformedResponseError(f"Could not parse Deriv historical candle: {exc}") from exc
        return sorted(parsed, key=lambda candle: candle.timestamp)

    async def get_instrument_metadata(self, symbol: str) -> InstrumentMetadata:
        item = await self._metadata(symbol)
        return InstrumentMetadata(
            symbol=symbol,
            display_name=item["display_name"],
            pip_size=item["pip_size"] or 0.01,
            asset_class="synthetic_index",
        )
