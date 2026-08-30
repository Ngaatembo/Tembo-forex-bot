"""
OANDA market data provider.

This is the REAL implementation — it makes actual HTTP calls to OANDA's
REST API. It requires MARKET_DATA_API_KEY (an OANDA API token) and
MARKET_DATA_ACCOUNT_ID to be set. Until then, get_market_data_provider()
keeps returning the mock (see market_data.py) — this class is never
constructed unless those credentials are present.

Docs: https://developer.oanda.com/rest-live-v20/instrument-ep/

Why OANDA specifically: free practice account with genuine market data,
a single well-documented REST API for both historical and streaming
prices, and no minimum deposit — a reasonable first broker for a solo
build. This choice lives entirely behind the MarketDataProvider
interface, so swapping to IG/FXCM/IBKR later touches only this file.
"""

from datetime import datetime, timezone

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.data_engine.market_data import Candle, InstrumentMetadata, MarketDataProvider

logger = get_logger(__name__)

# OANDA uses underscores, our system uses "EUR/USD" — this is the one
# place that translation happens, so the rest of the app never has to
# know about broker-specific symbol formats.
_SYMBOL_MAP = {
    "EUR/USD": "EUR_USD",
    "GBP/USD": "GBP_USD",
    "USD/JPY": "USD_JPY",
    "XAU/USD": "XAU_USD",
}

# Our internal timeframe strings -> OANDA's "granularity" codes
_GRANULARITY_MAP = {
    "1m": "M1",
    "5m": "M5",
    "15m": "M15",
    "1h": "H1",
    "4h": "H4",
    "1d": "D",
}

_PRACTICE_BASE_URL = "https://api-fxpractice.oanda.com/v3"
_LIVE_BASE_URL = "https://api-fxtrade.oanda.com/v3"


class OANDAProvider(MarketDataProvider):
    def __init__(self):
        settings = get_settings()
        if not settings.market_data_api_key:
            raise ValueError(
                "MARKET_DATA_API_KEY is required to use OANDAProvider. "
                "Set MARKET_DATA_PROVIDER=mock during development instead."
            )
        self._api_key = settings.market_data_api_key
        # Practice (demo) account by default — deliberately not tied to
        # ENABLE_LIVE_EXECUTION, since pulling historical data is safe
        # even on a live account; this only controls which OANDA
        # environment we read prices from.
        self._base_url = _PRACTICE_BASE_URL
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={"Authorization": f"Bearer {self._api_key}"},
            timeout=30.0,
        )

    async def get_current_price(self, symbol: str) -> float:
        oanda_symbol = _SYMBOL_MAP[symbol]
        resp = await self._client.get(f"/instruments/{oanda_symbol}/candles", params={"count": 1})
        resp.raise_for_status()
        candle = resp.json()["candles"][-1]
        return float(candle["mid"]["c"])

    async def get_candles(self, symbol: str, timeframe: str, limit: int = 500) -> list[Candle]:
        oanda_symbol = _SYMBOL_MAP[symbol]
        granularity = _GRANULARITY_MAP[timeframe]
        resp = await self._client.get(
            f"/instruments/{oanda_symbol}/candles",
            params={"granularity": granularity, "count": min(limit, 5000), "price": "M"},
        )
        resp.raise_for_status()
        return self._parse_candles(resp.json()["candles"], symbol, timeframe)

    async def get_historical_data(
        self, symbol: str, timeframe: str, start: datetime, end: datetime
    ) -> list[Candle]:
        oanda_symbol = _SYMBOL_MAP[symbol]
        granularity = _GRANULARITY_MAP[timeframe]

        all_candles: list[Candle] = []
        cursor = start

        # OANDA caps each request at 5000 candles, so a wide date range
        # needs multiple paginated requests. We page forward until we
        # pass `end`, logging (not silently swallowing) any gap OANDA
        # itself reports as missing data.
        while cursor < end:
            resp = await self._client.get(
                f"/instruments/{oanda_symbol}/candles",
                params={
                    "granularity": granularity,
                    "from": cursor.isoformat(),
                    "to": end.isoformat(),
                    "count": 5000,
                    "price": "M",
                },
            )
            if resp.status_code != 200:
                logger.error(
                    "OANDA historical request failed: %s %s", resp.status_code, resp.text
                )
                resp.raise_for_status()

            raw_candles = resp.json()["candles"]
            if not raw_candles:
                break

            batch = self._parse_candles(raw_candles, symbol, timeframe)
            all_candles.extend(batch)

            last_ts = batch[-1].timestamp
            if last_ts <= cursor:
                # Safety valve: if the cursor didn't advance, stop instead
                # of looping forever.
                break
            cursor = last_ts

        return all_candles

    async def get_instrument_metadata(self, symbol: str) -> InstrumentMetadata:
        pip_sizes = {"EUR/USD": 0.0001, "GBP/USD": 0.0001, "USD/JPY": 0.01, "XAU/USD": 0.01}
        return InstrumentMetadata(
            symbol=symbol, display_name=symbol, pip_size=pip_sizes.get(symbol, 0.0001)
        )

    @staticmethod
    def _parse_candles(raw_candles: list[dict], symbol: str, timeframe: str) -> list[Candle]:
        parsed = []
        for c in raw_candles:
            # OANDA marks incomplete/in-progress candles — never treat
            # one of those as a finished historical bar.
            if not c.get("complete", True):
                continue
            mid = c["mid"]
            parsed.append(
                Candle(
                    symbol=symbol,
                    timeframe=timeframe,
                    timestamp=datetime.fromisoformat(c["time"].replace("Z", "+00:00")).astimezone(
                        timezone.utc
                    ),
                    open=float(mid["o"]),
                    high=float(mid["h"]),
                    low=float(mid["l"]),
                    close=float(mid["c"]),
                    volume=float(c.get("volume", 0)),
                )
            )
        return parsed
