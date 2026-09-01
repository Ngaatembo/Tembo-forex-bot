"""
Builds a NewsContext for a given instrument — the single place that
enforces "UNAVAILABLE != NO_NEWS" and "DEMO data is never presented as
LIVE". Uses the TTL cache so repeated calls within the window don't
re-hit the provider.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from app.core.config import get_settings
from app.news_engine.cache import TTLCache
from app.news_engine.interfaces import get_economic_calendar_provider, get_news_provider
from app.news_engine.models import (
    CACHED, FRESH, NEWS_STATUS_CONFIRMED_NO_RELEVANT_NEWS, NEWS_STATUS_DEMO, NEWS_STATUS_LIVE,
    NEWS_STATUS_STALE, NEWS_STATUS_UNAVAILABLE, STALE, UNAVAILABLE, MacroEvent, NewsContext, NewsItem,
)

NEWS_CACHE_TTL_SECONDS = 12 * 60
NEWS_CACHE_STALE_GRACE_SECONDS = 15 * 60
CALENDAR_CACHE_TTL_SECONDS = 30 * 60
CALENDAR_CACHE_STALE_GRACE_SECONDS = 30 * 60

_news_cache: TTLCache = TTLCache(NEWS_CACHE_TTL_SECONDS, NEWS_CACHE_STALE_GRACE_SECONDS)
_calendar_cache: TTLCache = TTLCache(CALENDAR_CACHE_TTL_SECONDS, CALENDAR_CACHE_STALE_GRACE_SECONDS)
_last_successful_news_fetch: Optional[datetime] = None
_last_successful_calendar_fetch: Optional[datetime] = None


def _build_context(items: list, instrument: Optional[str], data_freshness: str, provider_name: str) -> NewsContext:
    """data_freshness is one of FRESH/CACHED/STALE (the cache's own
    vocabulary) — this maps it into NewsContext's status vocabulary,
    which is a genuinely different (larger) set of concepts."""
    if instrument is not None:
        relevant = tuple(i for i in items if instrument in i.relevant_instruments)
    else:
        relevant = tuple(items)

    if data_freshness == STALE:
        status = NEWS_STATUS_STALE
    elif instrument is not None and not relevant:
        # A genuine fetch succeeded and genuinely found nothing for
        # this specific instrument -- a real, positive finding, not an
        # outage. Distinct from UNAVAILABLE.
        status = NEWS_STATUS_CONFIRMED_NO_RELEVANT_NEWS
    else:
        status = NEWS_STATUS_LIVE

    return NewsContext(
        status=status, freshness=data_freshness, relevant_news=relevant,
        last_successful_fetch=_last_successful_news_fetch, provider=provider_name,
    )


async def get_news_context(instrument: Optional[str] = None) -> NewsContext:
    global _last_successful_news_fetch
    settings = get_settings()
    provider_name = settings.news_provider

    if provider_name == "mock":
        return NewsContext(
            status=NEWS_STATUS_DEMO, freshness=UNAVAILABLE, relevant_news=(),
            last_successful_fetch=None, provider="mock",
        )

    cached_items, freshness = _news_cache.get("recent")
    if cached_items is not None and freshness == FRESH:
        return _build_context(cached_items, instrument, freshness, provider_name)

    try:
        provider = get_news_provider(provider_name)
        items = await provider.get_recent_news(category="forex")
        _news_cache.set("recent", items)
        _last_successful_news_fetch = datetime.now(timezone.utc)
        return _build_context(items, instrument, FRESH, provider_name)
    except Exception as e:
        cached_items, freshness = _news_cache.get("recent")
        if cached_items is not None and freshness == STALE:
            return _build_context(cached_items, instrument, STALE, provider_name)
        return NewsContext(
            status=NEWS_STATUS_UNAVAILABLE, freshness=UNAVAILABLE, relevant_news=(),
            last_successful_fetch=_last_successful_news_fetch, provider=provider_name, error=str(e),
        )


async def get_upcoming_macro_events(lookahead_hours: float = 48) -> Optional[list]:
    """Returns None (not an empty list) when the calendar is genuinely
    unavailable — callers (e.g. macro_risk.py) must treat that as
    UNKNOWN risk, never as 'no events'."""
    global _last_successful_calendar_fetch
    settings = get_settings()
    provider_name = settings.economic_calendar_provider

    if provider_name == "mock":
        return None

    cached_events, freshness = _calendar_cache.get("upcoming")
    if cached_events is not None and freshness == FRESH:
        return cached_events

    try:
        provider = get_economic_calendar_provider(provider_name)
        now = datetime.now(timezone.utc)
        events = await provider.get_upcoming_events(now, now + timedelta(hours=lookahead_hours))
        _calendar_cache.set("upcoming", events)
        _last_successful_calendar_fetch = now
        return events
    except Exception:
        cached_events, freshness = _calendar_cache.get("upcoming")
        if cached_events is not None and freshness == STALE:
            return cached_events
        return None
