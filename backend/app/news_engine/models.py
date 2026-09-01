"""
Provider-neutral News + Economic Calendar models.

Every field here is something a real provider genuinely supplies, or
is explicitly None/documented-as-derived when it isn't. Nothing is
invented to make a card look complete.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

FRESH = "FRESH"
CACHED = "CACHED"
STALE = "STALE"
UNAVAILABLE = "UNAVAILABLE"

DATA_FRESHNESS_STATES = frozenset({FRESH, CACHED, STALE, UNAVAILABLE})


@dataclass(frozen=True)
class NewsItem:
    news_id: str
    timestamp: datetime
    headline: str
    summary: Optional[str]
    source: str
    url: Optional[str]
    category: Optional[str]
    relevant_instruments: tuple[str, ...]
    sentiment: Optional[float]
    provider: str


@dataclass(frozen=True)
class MacroEvent:
    event_id: str
    timestamp: datetime
    currency: Optional[str]
    country: Optional[str]
    event_name: str
    importance: str
    previous: Optional[float]
    forecast: Optional[float]
    actual: Optional[float]
    source: str
    url: Optional[str]


IMPORTANCE_LEVELS = frozenset({"HIGH", "MEDIUM", "LOW", "UNKNOWN"})

NEWS_STATUS_LIVE = "LIVE"
NEWS_STATUS_DEMO = "DEMO"
NEWS_STATUS_UNAVAILABLE = "UNAVAILABLE"
NEWS_STATUS_STALE = "STALE"
NEWS_STATUS_CONFIRMED_NO_RELEVANT_NEWS = "CONFIRMED_NO_RELEVANT_NEWS"

NEWS_CONTEXT_STATUSES = frozenset({
    NEWS_STATUS_LIVE, NEWS_STATUS_DEMO, NEWS_STATUS_UNAVAILABLE,
    NEWS_STATUS_STALE, NEWS_STATUS_CONFIRMED_NO_RELEVANT_NEWS,
})


@dataclass(frozen=True)
class NewsContext:
    status: str
    freshness: str
    relevant_news: tuple[NewsItem, ...]
    last_successful_fetch: Optional[datetime]
    provider: str
    error: Optional[str] = None

    def __post_init__(self):
        if self.status not in NEWS_CONTEXT_STATUSES:
            raise ValueError(f"Unknown NewsContext status {self.status!r}.")
        if self.freshness not in DATA_FRESHNESS_STATES:
            raise ValueError(f"Unknown freshness {self.freshness!r}.")


MACRO_RISK_HIGH = "HIGH"
MACRO_RISK_MEDIUM = "MEDIUM"
MACRO_RISK_LOW = "LOW"
MACRO_RISK_UNKNOWN = "UNKNOWN"

MACRO_RISK_LEVELS = frozenset({MACRO_RISK_HIGH, MACRO_RISK_MEDIUM, MACRO_RISK_LOW, MACRO_RISK_UNKNOWN})


@dataclass(frozen=True)
class MacroEventRisk:
    level: str
    reason: str
    triggering_events: tuple[MacroEvent, ...]
