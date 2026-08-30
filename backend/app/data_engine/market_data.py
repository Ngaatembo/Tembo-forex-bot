"""
Market data provider abstraction.

The rest of the application must depend only on this interface,
never on a specific vendor (OANDA, IG, FXCM, Interactive Brokers, ...).
This lets Phase 1 ship against a MockMarketDataProvider and swap in a
real provider later without touching downstream code.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Candle:
    symbol: str
    timeframe: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: Optional[float] = None


@dataclass
class InstrumentMetadata:
    symbol: str
    display_name: str
    pip_size: float
    asset_class: str = "forex"


class MarketDataProvider(ABC):
    """Interface every market data provider implementation must satisfy."""

    @abstractmethod
    async def get_current_price(self, symbol: str) -> float:
        ...

    @abstractmethod
    async def get_candles(
        self, symbol: str, timeframe: str, limit: int = 500
    ) -> list[Candle]:
        ...

    @abstractmethod
    async def get_historical_data(
        self, symbol: str, timeframe: str, start: datetime, end: datetime
    ) -> list[Candle]:
        ...

    @abstractmethod
    async def get_instrument_metadata(self, symbol: str) -> InstrumentMetadata:
        ...


class MockMarketDataProvider(MarketDataProvider):
    """
    Deterministic fake provider used for Phase 0/1 development and for
    unit tests, so nothing depends on network access or real credentials
    before a real provider is configured.
    """

    async def get_current_price(self, symbol: str) -> float:
        return 1.0000

    async def get_candles(self, symbol: str, timeframe: str, limit: int = 500) -> list[Candle]:
        return []

    async def get_historical_data(
        self, symbol: str, timeframe: str, start: datetime, end: datetime
    ) -> list[Candle]:
        return []

    async def get_instrument_metadata(self, symbol: str) -> InstrumentMetadata:
        return InstrumentMetadata(symbol=symbol, display_name=symbol, pip_size=0.0001)


def get_market_data_provider(provider_name: str) -> MarketDataProvider:
    """
    Factory. Phase 1 adds real implementations (OANDAProvider, etc.)
    and registers them here. Unknown/"mock" provider names fall back
    to the mock so the app never fails to start for lack of credentials.
    """
    if provider_name == "mock":
        return MockMarketDataProvider()
    if provider_name == "oanda":
        from app.data_engine.providers.oanda import OANDAProvider

        return OANDAProvider()
    raise NotImplementedError(
        f"Market data provider '{provider_name}' is not implemented yet. "
        "Falling back is intentionally not automatic — set "
        "MARKET_DATA_PROVIDER=mock explicitly during development."
    )
