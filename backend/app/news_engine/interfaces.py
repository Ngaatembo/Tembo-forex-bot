"""
Provider-neutral interfaces for news and economic-calendar data.
Mirrors app/data_engine/market_data.py's exact ABC + mock + factory
pattern deliberately, for consistency with the rest of the codebase.
"""

from abc import ABC, abstractmethod
from datetime import datetime

from app.news_engine.models import MacroEvent, NewsItem


class NewsProvider(ABC):
    @abstractmethod
    async def get_recent_news(self, category: str = "general", limit: int = 50) -> list[NewsItem]:
        ...


class EconomicCalendarProvider(ABC):
    @abstractmethod
    async def get_upcoming_events(self, start: datetime, end: datetime) -> list[MacroEvent]:
        ...


class MockNewsProvider(NewsProvider):
    async def get_recent_news(self, category: str = "general", limit: int = 50) -> list[NewsItem]:
        return []


class MockEconomicCalendarProvider(EconomicCalendarProvider):
    async def get_upcoming_events(self, start: datetime, end: datetime) -> list[MacroEvent]:
        return []


def get_news_provider(provider_name: str) -> NewsProvider:
    if provider_name == "mock":
        return MockNewsProvider()
    if provider_name == "finnhub":
        from app.news_engine.providers.finnhub_news import FinnhubNewsProvider

        return FinnhubNewsProvider()
    raise NotImplementedError(
        f"News provider '{provider_name}' is not implemented yet. "
        "Falling back is intentionally not automatic — set NEWS_PROVIDER=mock explicitly during development."
    )


def get_economic_calendar_provider(provider_name: str) -> EconomicCalendarProvider:
    if provider_name == "mock":
        return MockEconomicCalendarProvider()
    if provider_name == "finnhub":
        from app.news_engine.providers.finnhub_calendar import FinnhubEconomicCalendarProvider

        return FinnhubEconomicCalendarProvider()
    raise NotImplementedError(
        f"Economic calendar provider '{provider_name}' is not implemented yet. "
        "Falling back is intentionally not automatic — set ECONOMIC_CALENDAR_PROVIDER=mock explicitly during development."
    )
