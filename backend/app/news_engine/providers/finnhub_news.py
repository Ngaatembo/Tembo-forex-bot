"""
Finnhub news provider.

Documentation source: finnhub.io/docs/api/market-news, verified via
web search, corroborated by an independent real sample response (not
guessed). CONFIRMED response shape for GET /news?category={general|forex|crypto|merger}:

    [{"category": "...", "datetime": 1593106080, "headline": "...",
      "id": 15805925, "image": "...", "related": "DAL", "source": "...",
      "summary": "...", "url": "..."}, ...]

  - "datetime" is a UNIX timestamp (integer), NOT a string.
  - There is NO sentiment field on this endpoint — confirmed absent
    from the documented response attributes. sentiment stays None.
  - Auth: ?token=API_KEY query parameter (confirmed across every
    Finnhub endpoint example found).
  - category="forex" is a real, documented category — used here
    instead of "general" since Tembo only cares about forex-relevant news.
"""

from datetime import datetime, timezone
from typing import Optional

import httpx

from app.core.config import get_settings
from app.news_engine.interfaces import NewsProvider
from app.news_engine.models import NewsItem
from app.news_engine.relevance import instruments_relevant_to_text

_BASE_URL = "https://finnhub.io/api/v1"


class NewsProviderError(Exception):
    def __init__(self, message: str, api_key: Optional[str] = None):
        if api_key:
            message = message.replace(api_key, "[REDACTED]")
        super().__init__(message)


class NewsAuthenticationError(NewsProviderError):
    pass


class NewsRateLimitError(NewsProviderError):
    pass


class NewsProviderUnavailableError(NewsProviderError):
    pass


class NewsMalformedResponseError(NewsProviderError):
    pass


class FinnhubNewsProvider(NewsProvider):
    def __init__(self):
        settings = get_settings()
        if not settings.news_api_key:
            raise ValueError(
                "NEWS_API_KEY is required to use FinnhubNewsProvider. "
                "Set NEWS_PROVIDER=mock during development instead."
            )
        self._api_key = settings.news_api_key
        self._client = httpx.AsyncClient(base_url=_BASE_URL, timeout=30.0)

    def __repr__(self) -> str:
        return "FinnhubNewsProvider(api_key=[REDACTED])"

    async def get_recent_news(self, category: str = "forex", limit: int = 50) -> list[NewsItem]:
        try:
            resp = await self._client.get("/news", params={"category": category, "token": self._api_key})
        except httpx.TimeoutException as e:
            raise NewsProviderUnavailableError(f"Finnhub news request timed out: {e}", api_key=self._api_key) from e
        except httpx.HTTPError as e:
            raise NewsProviderUnavailableError(f"Network error calling Finnhub news: {e}", api_key=self._api_key) from e

        if resp.status_code == 401:
            raise NewsAuthenticationError("Finnhub authentication failed — check NEWS_API_KEY.", api_key=self._api_key)
        if resp.status_code == 429:
            raise NewsRateLimitError("Finnhub rate limit exceeded.", api_key=self._api_key)
        if resp.status_code != 200:
            raise NewsProviderUnavailableError(f"Finnhub returned HTTP {resp.status_code}: {resp.text[:300]}", api_key=self._api_key)

        try:
            raw_articles = resp.json()
            if not isinstance(raw_articles, list):
                raise NewsMalformedResponseError(f"Expected a list of articles, got: {type(raw_articles)}", api_key=self._api_key)
            return self._parse_articles(raw_articles[:limit])
        except (ValueError, KeyError, TypeError) as e:
            raise NewsMalformedResponseError(f"Could not parse Finnhub news response: {e}", api_key=self._api_key) from e

    @staticmethod
    def _parse_articles(raw_articles: list[dict]) -> list[NewsItem]:
        items = []
        seen_ids = set()
        for a in raw_articles:
            news_id = str(a["id"])
            if news_id in seen_ids:
                continue
            seen_ids.add(news_id)

            headline = a["headline"]
            summary = a.get("summary") or None
            items.append(
                NewsItem(
                    news_id=news_id,
                    timestamp=datetime.fromtimestamp(a["datetime"], tz=timezone.utc),
                    headline=headline,
                    summary=summary,
                    source=a.get("source", "unknown"),
                    url=a.get("url") or None,
                    category=a.get("category"),
                    relevant_instruments=instruments_relevant_to_text(headline, summary),
                    sentiment=None,
                    provider="finnhub",
                )
            )
        return items
