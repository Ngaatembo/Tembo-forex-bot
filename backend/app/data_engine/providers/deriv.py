"""Read-only Deriv market-data adapter for forex and gold.

Uses Deriv's public WebSocket market-data endpoint. No account token is
required for this module. Account authentication and trading stay in the
separate integrations/deriv.py module and remain demo-only.

The adapter discovers Deriv's active symbol catalogue instead of hard-coding
broker symbol IDs, then maps Tembo instruments such as EUR/USD and XAU/USD to
the currently active Deriv underlying symbol.
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone

import websockets

from app.core.config import get_settings
from app.data_engine.market_data import Candle, InstrumentMetadata, MarketDataProvider

DERIV_PUBLIC_WS = "wss://api.derivws.com/trading/v1/options/ws/public"

_TIMEFRAME_GRANULARITY = {
    "m5": 300,
    "m15": 900,
    "h1": 3600,
    "h4": 14400,
    "d1": 86400,
}

_SUPPORTED_INSTRUMENTS = {
    "EUR/USD": {"EURUSD"},
    "GBP/USD": {"GBPUSD"},
    "USD/JPY": {"USDJPY"},
    "XAU/USD": {"XAUUSD", "GOLDUSD"},
}

_PIP_SIZES = {
    "EUR/USD": 0.0001,
    "GBP/USD": 0.0001,
    "USD/JPY": 0.01,
    "XAU/USD": 0.01,
}


class DerivMarketDataError(RuntimeError):
    pass


class UnsupportedInstrumentError(DerivMarketDataError):
    pass


class UnsupportedTimeframeError(DerivMarketDataError):
    pass


class MalformedResponseError(DerivMarketDataError):
    pass


class DerivMarketDataProvider(MarketDataProvider):
    _symbols_cache: tuple[float, list[dict]] | None = None
    _symbols_ttl = 300.0
    _price_cache: dict[str, tuple[float, float]] = {}
    _price_ttl = 2.0
    _candles_cache: dict[tuple[str, str, int], tuple[float, list[Candle]]] = {}
    _candles_ttl = 20.0

    def __init__(self):
        settings = get_settings()
        self._ws_url = settings.deriv_public_ws_url or DERIV_PUBLIC_WS

    async def _request(self, payload: dict, expected_type: str) -> dict:
        # Deriv recommends pacing and backing off after rejected requests.
        # Public market-data calls are otherwise stateless, so a fresh
        # connection is safe for a small number of transient retries.
        retryable_codes = {"WrongResponse", "RateLimit", "InternalServerError"}
        last_error: Exception | None = None

        for attempt in range(3):
            try:
                async with websockets.connect(
                    self._ws_url, open_timeout=15, close_timeout=5
                ) as ws:
                    await ws.send(json.dumps(payload))
                    deadline = time.monotonic() + 20
                    while time.monotonic() < deadline:
                        raw = await ws.recv()
                        response = json.loads(raw)
                        if response.get("error"):
                            error = response["error"]
                            code = str(error.get("code") or "")
                            message = str(error.get("message") or "Unknown Deriv error")
                            if code in retryable_codes and attempt < 2:
                                await asyncio.sleep(1.5 * (attempt + 1))
                                break
                            raise DerivMarketDataError(
                                f"Deriv API error {code}: {message}"
                            )
                        if response.get("msg_type") == expected_type:
                            return response
                    else:
                        raise DerivMarketDataError(
                            f"Timed out waiting for Deriv {expected_type} response."
                        )
            except DerivMarketDataError as exc:
                last_error = exc
                if attempt >= 2:
                    raise
            except Exception as exc:
                last_error = exc
                if attempt >= 2:
                    raise DerivMarketDataError(
                        f"Deriv public market-data connection failed: {exc}"
                    ) from exc
            await asyncio.sleep(1.5 * (attempt + 1))

        raise DerivMarketDataError(
            f"Deriv public market-data request failed after retries: {last_error}"
        )

    @staticmethod
    def _normalize(value: object) -> str:
        return "".join(ch for ch in str(value or "").upper() if ch.isalnum())

    async def get_active_markets(self) -> list[dict]:
        cached = self._symbols_cache
        now = time.monotonic()
        if cached and now - cached[0] < self._symbols_ttl:
            return [dict(item) for item in cached[1]]

        response = await self._request(
            {"active_symbols": "brief", "req_id": 11},
            "active_symbols",
        )
        records = response.get("active_symbols")
        if not isinstance(records, list):
            raise MalformedResponseError(
                "Deriv active_symbols response is missing a list."
            )

        markets: list[dict] = []
        for item in records:
            if not isinstance(item, dict) or item.get("is_trading_suspended"):
                continue
            underlying = item.get("underlying_symbol")
            if not underlying:
                continue
            markets.append(
                {
                    "underlying_symbol": str(underlying),
                    "display_name": item.get("underlying_symbol_name") or underlying,
                    "symbol": item.get("symbol") or underlying,
                    "underlying_symbol_type": item.get("underlying_symbol_type"),
                    "market": item.get("market"),
                    "pip_size": float(item.get("pip_size") or 0),
                    "exchange_is_open": bool(item.get("exchange_is_open", 1)),
                }
            )

        if not markets:
            raise MalformedResponseError("Deriv returned no active market symbols.")

        self._symbols_cache = (time.monotonic(), markets)
        return [dict(item) for item in markets]

    async def _resolve_symbol(self, symbol: str) -> dict:
        aliases = _SUPPORTED_INSTRUMENTS.get(symbol)
        if aliases is None:
            raise UnsupportedInstrumentError(
                f"Instrument {symbol!r} is not supported by the Deriv market-data adapter."
            )

        markets = await self.get_active_markets()
        for item in markets:
            values = {
                self._normalize(item.get("underlying_symbol")),
                self._normalize(item.get("symbol")),
                self._normalize(item.get("display_name")),
            }
            # The current Deriv API commonly exposes forex underlyings with
            # an FRX prefix (for example frxEURUSD), while Tembo's canonical
            # aliases are EURUSD/GBPUSD/USDJPY. Match both representations.
            values_without_frx = {
                value[3:] for value in values if value.startswith("FRX")
            }
            if values.intersection(aliases) or values_without_frx.intersection(aliases):
                return item

        raise UnsupportedInstrumentError(
            f"Deriv does not currently expose an active symbol for {symbol!r}."
        )

    @staticmethod
    def _granularity(timeframe: str) -> int:
        try:
            return _TIMEFRAME_GRANULARITY[timeframe.lower()]
        except KeyError as exc:
            raise UnsupportedTimeframeError(
                f"Timeframe {timeframe!r} is not supported. "
                f"Allowed: {sorted(_TIMEFRAME_GRANULARITY)}."
            ) from exc

    async def get_current_price(self, symbol: str) -> float:
        resolved = await self._resolve_symbol(symbol)
        cached = self._price_cache.get(symbol)
        now = time.monotonic()
        if cached and now - cached[0] < self._price_ttl:
            return cached[1]

        response = await self._request(
            {"ticks": resolved["underlying_symbol"] , "req_id": 12},
            "tick",
        )
        try:
            price = float(response["tick"]["quote"])
        except (KeyError, TypeError, ValueError) as exc:
            raise MalformedResponseError(
                "Deriv tick response did not contain a numeric quote."
            ) from exc

        self._price_cache[symbol] = (time.monotonic(), price)
        return price

    async def get_candles(
        self, symbol: str, timeframe: str, limit: int = 500
    ) -> list[Candle]:
        resolved = await self._resolve_symbol(symbol)
        granularity = self._granularity(timeframe)
        count = min(max(limit, 1), 5000)
        cache_key = (symbol, timeframe.lower(), count)
        cached = self._candles_cache.get(cache_key)
        now = time.monotonic()
        if cached and now - cached[0] < self._candles_ttl:
            return list(cached[1])

        response = await self._request(
            {
                "ticks_history": resolved["underlying_symbol"],
                "end": "latest",
                "count": count,
                "style": "candles",
                "granularity": granularity,
                "req_id": 13,
            },
            "candles",
        )
        raw = response.get("candles")
        if not isinstance(raw, list):
            raise MalformedResponseError(
                "Deriv candle response is missing a list."
            )

        parsed: list[Candle] = []
        try:
            for item in raw:
                parsed.append(
                    Candle(
                        symbol=symbol,
                        timeframe=timeframe.lower(),
                        timestamp=datetime.fromtimestamp(
                            int(item["epoch"]), tz=timezone.utc
                        ),
                        open=float(item["open"]),
                        high=float(item["high"]),
                        low=float(item["low"]),
                        close=float(item["close"]),
                        volume=None,
                    )
                )
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise MalformedResponseError(
                f"Could not parse Deriv candles: {exc}"
            ) from exc

        parsed.sort(key=lambda candle: candle.timestamp)
        self._candles_cache[cache_key] = (time.monotonic(), parsed)
        return list(parsed)

    async def get_historical_data(
        self, symbol: str, timeframe: str, start: datetime, end: datetime
    ) -> list[Candle]:
        resolved = await self._resolve_symbol(symbol)
        granularity = self._granularity(timeframe)
        response = await self._request(
            {
                "ticks_history": resolved["underlying_symbol"],
                "start": int(start.astimezone(timezone.utc).timestamp()),
                "end": int(end.astimezone(timezone.utc).timestamp()),
                "style": "candles",
                "granularity": granularity,
                "req_id": 14,
            },
            "candles",
        )
        raw = response.get("candles")
        if not isinstance(raw, list):
            raise MalformedResponseError(
                "Deriv historical candle response is missing a list."
            )

        parsed: list[Candle] = []
        try:
            for item in raw:
                parsed.append(
                    Candle(
                        symbol=symbol,
                        timeframe=timeframe.lower(),
                        timestamp=datetime.fromtimestamp(
                            int(item["epoch"]), tz=timezone.utc
                        ),
                        open=float(item["open"]),
                        high=float(item["high"]),
                        low=float(item["low"]),
                        close=float(item["close"]),
                        volume=None,
                    )
                )
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise MalformedResponseError(
                f"Could not parse Deriv historical candles: {exc}"
            ) from exc

        return sorted(parsed, key=lambda candle: candle.timestamp)

    async def get_instrument_metadata(self, symbol: str) -> InstrumentMetadata:
        resolved = await self._resolve_symbol(symbol)
        return InstrumentMetadata(
            symbol=symbol,
            display_name=resolved["display_name"],
            pip_size=_PIP_SIZES[symbol],
            asset_class="metals" if symbol == "XAU/USD" else "forex",
        )
