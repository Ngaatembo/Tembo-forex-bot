"""
Finnhub economic calendar provider.

Documentation source: Finnhub's own OpenAPI-generated Go client model
(finnhub-go/model_economic_event.go, sourced from finnhub.io/docs/api),
confirming the real field names — verified via web search, not guessed:

    {"actual": <float|null>, "prev": <float|null>, "country": <string>,
     "unit": <string>, "estimate": <float|null>, "event": <string>,
     "impact": <string>, "time": <string>}

HONEST LIMITATIONS on this endpoint specifically, lower confidence
than the news endpoint above:
  - No fully-confirmed example response body or exact endpoint path
    string was found (finnhub.io/docs/api/economic-calendar returned
    only site navigation, not example JSON) — the field NAMES above
    are confirmed from Finnhub's own official client library, but the
    exact "impact" value vocabulary (e.g. "high"/"low" vs "1"/"2"/"3")
    was not independently confirmed. _normalize_importance() below is
    written defensively for both possibilities and maps anything
    genuinely unrecognized to "UNKNOWN" rather than guessing.
  - Finnhub provides NO unique event ID for economic events (unlike
    news, which has "id"). event_id here is DERIVED (country + event +
    time, hashed) — documented explicitly as Tembo's own construction,
    never presented as provider-supplied.
  - Finnhub provides NO currency field, only "country" — currency is
    derived via relevance.py's documented COUNTRY_TO_CURRENCY mapping,
    not invented per-event.
"""

import hashlib
from datetime import datetime, timezone
from typing import Optional

import httpx

from app.core.config import get_settings
from app.news_engine.interfaces import EconomicCalendarProvider
from app.news_engine.models import MacroEvent
from app.news_engine.providers.finnhub_news import (
    NewsAuthenticationError, NewsMalformedResponseError, NewsProviderUnavailableError, NewsRateLimitError,
)
from app.news_engine.relevance import currency_for_country

_BASE_URL = "https://finnhub.io/api/v1"

_HIGH_TERMS = {"high", "3"}
_MEDIUM_TERMS = {"medium", "med", "2"}
_LOW_TERMS = {"low", "1"}


def _normalize_importance(raw) -> str:
    if raw is None:
        return "UNKNOWN"
    value = str(raw).strip().lower()
    if value in _HIGH_TERMS:
        return "HIGH"
    if value in _MEDIUM_TERMS:
        return "MEDIUM"
    if value in _LOW_TERMS:
        return "LOW"
    return "UNKNOWN"


def _derive_event_id(country: Optional[str], event_name: str, time_str: str) -> str:
    raw = f"{country}|{event_name}|{time_str}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


class FinnhubEconomicCalendarProvider(EconomicCalendarProvider):
    def __init__(self):
        settings = get_settings()
        if not settings.economic_calendar_api_key:
            raise ValueError(
                "ECONOMIC_CALENDAR_API_KEY is required to use FinnhubEconomicCalendarProvider. "
                "Set ECONOMIC_CALENDAR_PROVIDER=mock during development instead."
            )
        self._api_key = settings.economic_calendar_api_key
        self._client = httpx.AsyncClient(base_url=_BASE_URL, timeout=30.0)

    def __repr__(self) -> str:
        return "FinnhubEconomicCalendarProvider(api_key=[REDACTED])"

    async def get_upcoming_events(self, start: datetime, end: datetime) -> list[MacroEvent]:
        try:
            resp = await self._client.get(
                "/calendar/economic",
                params={"from": start.strftime("%Y-%m-%d"), "to": end.strftime("%Y-%m-%d"), "token": self._api_key},
            )
        except httpx.TimeoutException as e:
            raise NewsProviderUnavailableError(f"Finnhub calendar request timed out: {e}", api_key=self._api_key) from e
        except httpx.HTTPError as e:
            raise NewsProviderUnavailableError(f"Network error calling Finnhub calendar: {e}", api_key=self._api_key) from e

        if resp.status_code == 401:
            raise NewsAuthenticationError("Finnhub authentication failed — check ECONOMIC_CALENDAR_API_KEY.", api_key=self._api_key)
        if resp.status_code == 429:
            raise NewsRateLimitError("Finnhub rate limit exceeded.", api_key=self._api_key)
        if resp.status_code != 200:
            raise NewsProviderUnavailableError(f"Finnhub returned HTTP {resp.status_code}: {resp.text[:300]}", api_key=self._api_key)

        try:
            body = resp.json()
            raw_events = body.get("economicCalendar", body) if isinstance(body, dict) else body
            if not isinstance(raw_events, list):
                raise NewsMalformedResponseError(f"Expected a list of economic events, got: {type(raw_events)}", api_key=self._api_key)
            return self._parse_events(raw_events)
        except (ValueError, KeyError, TypeError) as e:
            raise NewsMalformedResponseError(f"Could not parse Finnhub calendar response: {e}", api_key=self._api_key) from e

    @staticmethod
    def _parse_events(raw_events: list[dict]) -> list[MacroEvent]:
        events = []
        seen_ids = set()
        for e in raw_events:
            time_str = e.get("time")
            event_name = e.get("event")
            if not time_str or not event_name:
                continue

            try:
                timestamp = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            except ValueError:
                continue

            country = e.get("country")
            event_id = _derive_event_id(country, event_name, time_str)
            if event_id in seen_ids:
                continue
            seen_ids.add(event_id)

            events.append(
                MacroEvent(
                    event_id=event_id,
                    timestamp=timestamp,
                    currency=currency_for_country(country),
                    country=country,
                    event_name=event_name,
                    importance=_normalize_importance(e.get("impact")),
                    previous=e.get("prev"),
                    forecast=e.get("estimate"),
                    actual=e.get("actual"),
                    source="finnhub",
                    url=None,
                )
            )
        return events
