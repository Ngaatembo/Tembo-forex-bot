"""
Twelve Data market data provider.

Real, sourced Twelve Data API documentation used (August 2026,
verified via web search against twelvedata.com/docs and independent
corroborating sources — not guessed):
  - GET https://api.twelvedata.com/price?symbol=EUR/USD&apikey=...
    -> {"price": "1.10234"}
  - GET https://api.twelvedata.com/time_series?symbol=EUR/USD&interval=1h&outputsize=N&apikey=...
    -> {"meta": {...}, "values": [{"datetime": "...", "open": "...",
       "high": "...", "low": "...", "close": "...", "volume": "..."}, ...],
       "status": "ok"}
    IMPORTANT: every OHLCV field is returned as a STRING, not a
    number — confirmed directly from the documented example response,
    not assumed. Explicitly cast to float here.
  - Errors: JSON body with "code", "message", "status" keys; HTTP 401
    for invalid API key, HTTP 429 for rate limiting (also documented).
  - Symbol format: Twelve Data accepts "EUR/USD"-style symbols
    directly (their own docs example uses "XAU/USD") — this already
    matches Tembo's internal convention, unlike OANDA which needs an
    underscore translation. No symbol mapping dict is needed here,
    only a supported-instrument allowlist (see _to_provider_symbol).
  - Interval strings ("5min", "15min", "1h", "4h", "1day") are Twelve
    Data's own standard, consistent vocabulary documented across every
    endpoint reference and client library found.

WHAT TWELVE DATA DOES NOT PROVIDE: no documented endpoint returns a
forex "pip size" directly. get_instrument_metadata() below reuses the
SAME reasoned pip-size table already established in oanda.py — this
is Tembo's own internal convention, not a claim that Twelve Data
supplies it. Documented honestly, not silently presented as
provider-sourced data.
"""

from datetime import datetime, timezone
from typing import Optional

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.data_engine.market_data import Candle, InstrumentMetadata, MarketDataProvider

logger = get_logger(__name__)

_BASE_URL = "https://api.twelvedata.com"

_INTERVAL_MAP = {
    "m5": "5min", "m15": "15min", "h1": "1h", "h4": "4h", "d1": "1day",
}

_SUPPORTED_INSTRUMENTS = {"EUR/USD", "GBP/USD", "USD/JPY", "XAU/USD"}

_PIP_SIZES = {"EUR/USD": 0.0001, "GBP/USD": 0.0001, "USD/JPY": 0.01, "XAU/USD": 0.01}


class TwelveDataProviderError(Exception):
    def __init__(self, message: str, api_key: Optional[str] = None):
        if api_key:
            message = message.replace(api_key, "[REDACTED]")
        super().__init__(message)


class AuthenticationError(TwelveDataProviderError):
    pass


class RateLimitError(TwelveDataProviderError):
    pass


class ProviderTimeoutError(TwelveDataProviderError):
    pass


class ProviderConnectionError(TwelveDataProviderError):
    pass


class MalformedResponseError(TwelveDataProviderError):
    pass


class UnsupportedInstrumentError(TwelveDataProviderError):
    pass


class UnsupportedTimeframeError(TwelveDataProviderError):
    pass


class TwelveDataProvider(MarketDataProvider):
    def __init__(self):
        settings = get_settings()
        if not settings.market_data_api_key:
            raise ValueError(
                "MARKET_DATA_API_KEY is required to use TwelveDataProvider. "
                "Set MARKET_DATA_PROVIDER=mock during development instead."
            )
        self._api_key = settings.market_data_api_key
        self._client = httpx.AsyncClient(base_url=_BASE_URL, timeout=30.0)

    def __repr__(self) -> str:
        return "TwelveDataProvider(api_key=[REDACTED])"

    def _to_provider_symbol(self, symbol: str) -> str:
        if symbol not in _SUPPORTED_INSTRUMENTS:
            raise UnsupportedInstrumentError(
                f"Instrument {symbol!r} is not in Tembo's supported set {sorted(_SUPPORTED_INSTRUMENTS)}."
            )
        return symbol

    def _to_provider_interval(self, timeframe: str) -> str:
        if timeframe not in _INTERVAL_MAP:
            raise UnsupportedTimeframeError(
                f"Timeframe {timeframe!r} is not supported. Allowed: {sorted(_INTERVAL_MAP.keys())}."
            )
        return _INTERVAL_MAP[timeframe]

    async def _get(self, path: str, params: dict) -> dict:
        params = {**params, "apikey": self._api_key}
        try:
            resp = await self._client.get(path, params=params)
        except httpx.TimeoutException as e:
            raise ProviderTimeoutError(f"Twelve Data request to {path} timed out: {e}", api_key=self._api_key) from e
        except httpx.ConnectError as e:
            raise ProviderConnectionError(f"Could not connect to Twelve Data ({path}): {e}", api_key=self._api_key) from e
        except httpx.HTTPError as e:
            raise ProviderConnectionError(f"Network error calling Twelve Data ({path}): {e}", api_key=self._api_key) from e

        if resp.status_code == 401:
            raise AuthenticationError("Twelve Data authentication failed — check MARKET_DATA_API_KEY.", api_key=self._api_key)
        if resp.status_code == 429:
            raise RateLimitError("Twelve Data rate limit exceeded.", api_key=self._api_key)
        if resp.status_code != 200:
            raise TwelveDataProviderError(
                f"Twelve Data returned HTTP {resp.status_code}: {resp.text[:300]}", api_key=self._api_key
            )

        body = resp.json()
        if isinstance(body, dict) and body.get("status") == "error":
            raise TwelveDataProviderError(
                f"Twelve Data error {body.get('code')}: {body.get('message')}", api_key=self._api_key
            )
        return body

    async def get_current_price(self, symbol: str) -> float:
        provider_symbol = self._to_provider_symbol(symbol)
        body = await self._get("/price", {"symbol": provider_symbol})
        if "price" not in body:
            raise MalformedResponseError(f"Twelve Data /price response missing 'price' field: {body}", api_key=self._api_key)
        return float(body["price"])

    async def get_candles(self, symbol: str, timeframe: str, limit: int = 500) -> list[Candle]:
        provider_symbol = self._to_provider_symbol(symbol)
        interval = self._to_provider_interval(timeframe)
        body = await self._get(
            "/time_series", {"symbol": provider_symbol, "interval": interval, "outputsize": min(limit, 5000)}
        )
        if "values" not in body:
            raise MalformedResponseError(f"Twelve Data /time_series response missing 'values' field: {body}", api_key=self._api_key)
        return self._parse_candles(body["values"], symbol, timeframe)

    async def get_historical_data(self, symbol: str, timeframe: str, start: datetime, end: datetime) -> list[Candle]:
        provider_symbol = self._to_provider_symbol(symbol)
        interval = self._to_provider_interval(timeframe)
        body = await self._get(
            "/time_series",
            {
                "symbol": provider_symbol, "interval": interval, "outputsize": 5000,
                "start_date": start.strftime("%Y-%m-%d %H:%M:%S"), "end_date": end.strftime("%Y-%m-%d %H:%M:%S"),
            },
        )
        if "values" not in body:
            raise MalformedResponseError(f"Twelve Data /time_series response missing 'values' field: {body}", api_key=self._api_key)
        return self._parse_candles(body["values"], symbol, timeframe)

    async def get_instrument_metadata(self, symbol: str) -> InstrumentMetadata:
        self._to_provider_symbol(symbol)
        return InstrumentMetadata(symbol=symbol, display_name=symbol, pip_size=_PIP_SIZES.get(symbol, 0.0001))

    @staticmethod
    def _parse_candles(raw_values: list[dict], symbol: str, timeframe: str) -> list[Candle]:
        try:
            parsed = [
                Candle(
                    symbol=symbol, timeframe=timeframe,
                    timestamp=datetime.strptime(v["datetime"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc),
                    open=float(v["open"]), high=float(v["high"]), low=float(v["low"]), close=float(v["close"]),
                    volume=float(v["volume"]) if v.get("volume") not in (None, "") else None,
                )
                for v in raw_values
            ]
        except (KeyError, ValueError, TypeError) as e:
            raise MalformedResponseError(f"Could not parse Twelve Data candle values: {e}")
        parsed.reverse()
        return parsed
