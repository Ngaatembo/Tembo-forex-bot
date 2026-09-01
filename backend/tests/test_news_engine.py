from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.news_engine.models import (
    MACRO_RISK_HIGH, MACRO_RISK_LOW, MACRO_RISK_MEDIUM, MACRO_RISK_UNKNOWN,
    MacroEvent, NewsContext, NewsItem,
)
from app.news_engine.relevance import (
    currency_for_country, instruments_relevant_to_currency, instruments_relevant_to_text,
)
from app.news_engine.macro_risk import compute_macro_event_risk


def mock_response(status_code, json_data):
    return httpx.Response(status_code, json=json_data, request=httpx.Request("GET", "https://finnhub.io/api/v1/x"))


def make_event(currency="USD", importance="HIGH", hours_from_now=1.0, event_name="US CPI"):
    return MacroEvent(
        event_id="evt1", timestamp=datetime.now(timezone.utc) + timedelta(hours=hours_from_now),
        currency=currency, country="US", event_name=event_name, importance=importance,
        previous=1.0, forecast=1.1, actual=None, source="finnhub", url=None,
    )


def test_news_context_rejects_unknown_status():
    with pytest.raises(ValueError):
        NewsContext(status="NOT_REAL", freshness="FRESH", relevant_news=(), last_successful_fetch=None, provider="mock")


def test_news_context_rejects_unknown_freshness():
    with pytest.raises(ValueError):
        NewsContext(status="LIVE", freshness="NOT_REAL", relevant_news=(), last_successful_fetch=None, provider="mock")


def test_usd_keyword_maps_to_all_four_instruments():
    result = instruments_relevant_to_text("Federal Reserve raises interest rates", None)
    assert set(result) == {"EUR/USD", "GBP/USD", "USD/JPY", "XAU/USD"}


def test_eur_keyword_maps_only_to_eurusd():
    result = instruments_relevant_to_text("ECB holds rates steady", None)
    assert result == ("EUR/USD",)


def test_gold_keyword_maps_to_xauusd_only():
    result = instruments_relevant_to_text("Gold prices surge on safe-haven demand", None)
    assert result == ("XAU/USD",)


def test_irrelevant_article_maps_to_nothing():
    result = instruments_relevant_to_text("Local bakery wins award", None)
    assert result == ()


def test_country_to_currency_mapping():
    assert currency_for_country("US") == "USD"
    assert currency_for_country("United States") == "USD"
    assert currency_for_country("Japan") == "JPY"
    assert currency_for_country("Atlantis") is None


def test_instruments_relevant_to_currency():
    assert set(instruments_relevant_to_currency("USD")) == {"EUR/USD", "GBP/USD", "USD/JPY", "XAU/USD"}
    assert instruments_relevant_to_currency("GBP") == ("GBP/USD",)


def test_calendar_unavailable_yields_unknown_never_low():
    risk = compute_macro_event_risk("EUR/USD", upcoming_events=None)
    assert risk.level == MACRO_RISK_UNKNOWN
    assert risk.level != MACRO_RISK_LOW


def test_high_impact_event_within_window_yields_high():
    events = [make_event(currency="USD", importance="HIGH", hours_from_now=1.0)]
    risk = compute_macro_event_risk("EUR/USD", upcoming_events=events, protection_window_hours=2)
    assert risk.level == MACRO_RISK_HIGH
    assert len(risk.triggering_events) == 1


def test_high_impact_event_outside_window_does_not_force_high():
    events = [make_event(currency="USD", importance="HIGH", hours_from_now=20.0)]
    risk = compute_macro_event_risk("EUR/USD", upcoming_events=events, protection_window_hours=2)
    assert risk.level != MACRO_RISK_HIGH


def test_irrelevant_currency_event_ignored():
    events = [make_event(currency="JPY", importance="HIGH", hours_from_now=1.0)]
    risk = compute_macro_event_risk("EUR/USD", upcoming_events=events, protection_window_hours=2)
    assert risk.level != MACRO_RISK_HIGH


def test_no_events_yields_low():
    risk = compute_macro_event_risk("EUR/USD", upcoming_events=[])
    assert risk.level == MACRO_RISK_LOW


def test_medium_event_later_yields_medium():
    events = [make_event(currency="USD", importance="MEDIUM", hours_from_now=5.0)]
    risk = compute_macro_event_risk("EUR/USD", upcoming_events=events, protection_window_hours=2)
    assert risk.level == MACRO_RISK_MEDIUM


def test_macro_risk_never_produces_a_buy_sell_signal():
    risk = compute_macro_event_risk("EUR/USD", upcoming_events=[])
    assert not hasattr(risk, "direction")
    assert not hasattr(risk, "signal")


@pytest.fixture
def news_provider(monkeypatch):
    from app.core.config import get_settings
    get_settings.cache_clear()
    monkeypatch.setenv("NEWS_PROVIDER", "finnhub")
    monkeypatch.setenv("NEWS_API_KEY", "fake_test_key_never_real")
    from app.news_engine.providers.finnhub_news import FinnhubNewsProvider
    p = FinnhubNewsProvider()
    yield p
    get_settings.cache_clear()


def test_news_provider_requires_api_key(monkeypatch):
    from app.core.config import get_settings
    get_settings.cache_clear()
    monkeypatch.setenv("NEWS_PROVIDER", "finnhub")
    monkeypatch.delenv("NEWS_API_KEY", raising=False)
    from app.news_engine.providers.finnhub_news import FinnhubNewsProvider
    with pytest.raises(ValueError):
        FinnhubNewsProvider()
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_news_provider_parses_real_confirmed_shape(news_provider):
    fake_body = [
        {"category": "forex", "datetime": 1593106080, "headline": "Fed raises rates", "id": 15805925,
         "image": "http://x", "related": "", "source": "reuters", "summary": "The Fed raised rates.", "url": "http://x"},
    ]
    fake_resp = mock_response(200, fake_body)
    with patch.object(news_provider._client, "get", new=AsyncMock(return_value=fake_resp)):
        items = await news_provider.get_recent_news()
    assert len(items) == 1
    assert items[0].headline == "Fed raises rates"
    assert items[0].sentiment is None
    assert "EUR/USD" in items[0].relevant_instruments


@pytest.mark.asyncio
async def test_news_provider_deduplicates_by_id(news_provider):
    fake_body = [
        {"category": "forex", "datetime": 1593106080, "headline": "A", "id": 1, "source": "x", "summary": "", "url": ""},
        {"category": "forex", "datetime": 1593106080, "headline": "A", "id": 1, "source": "x", "summary": "", "url": ""},
    ]
    fake_resp = mock_response(200, fake_body)
    with patch.object(news_provider._client, "get", new=AsyncMock(return_value=fake_resp)):
        items = await news_provider.get_recent_news()
    assert len(items) == 1


@pytest.mark.asyncio
async def test_news_provider_malformed_response(news_provider):
    from app.news_engine.providers.finnhub_news import NewsMalformedResponseError
    fake_resp = mock_response(200, {"not": "a list"})
    with patch.object(news_provider._client, "get", new=AsyncMock(return_value=fake_resp)):
        with pytest.raises(NewsMalformedResponseError):
            await news_provider.get_recent_news()


@pytest.mark.asyncio
async def test_news_provider_auth_error(news_provider):
    from app.news_engine.providers.finnhub_news import NewsAuthenticationError
    fake_resp = mock_response(401, {"error": "invalid token"})
    with patch.object(news_provider._client, "get", new=AsyncMock(return_value=fake_resp)):
        with pytest.raises(NewsAuthenticationError):
            await news_provider.get_recent_news()


@pytest.mark.asyncio
async def test_news_provider_rate_limit(news_provider):
    from app.news_engine.providers.finnhub_news import NewsRateLimitError
    fake_resp = mock_response(429, {"error": "rate limited"})
    with patch.object(news_provider._client, "get", new=AsyncMock(return_value=fake_resp)):
        with pytest.raises(NewsRateLimitError):
            await news_provider.get_recent_news()


def test_news_api_key_never_in_repr(news_provider):
    assert news_provider._api_key not in repr(news_provider)


@pytest.fixture
def calendar_provider(monkeypatch):
    from app.core.config import get_settings
    get_settings.cache_clear()
    monkeypatch.setenv("ECONOMIC_CALENDAR_PROVIDER", "finnhub")
    monkeypatch.setenv("ECONOMIC_CALENDAR_API_KEY", "fake_test_key_never_real")
    from app.news_engine.providers.finnhub_calendar import FinnhubEconomicCalendarProvider
    p = FinnhubEconomicCalendarProvider()
    yield p
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_calendar_provider_parses_confirmed_field_names(calendar_provider):
    fake_body = {"economicCalendar": [
        {"actual": None, "prev": 3.1, "country": "US", "unit": "%", "estimate": 3.2,
         "event": "CPI YoY", "impact": "high", "time": "2026-09-15 12:30:00"},
    ]}
    fake_resp = mock_response(200, fake_body)
    with patch.object(calendar_provider._client, "get", new=AsyncMock(return_value=fake_resp)):
        events = await calendar_provider.get_upcoming_events(datetime.now(timezone.utc), datetime.now(timezone.utc) + timedelta(days=2))
    assert len(events) == 1
    assert events[0].event_name == "CPI YoY"
    assert events[0].importance == "HIGH"
    assert events[0].currency == "USD"


@pytest.mark.asyncio
async def test_calendar_provider_unrecognized_impact_is_unknown_not_guessed(calendar_provider):
    fake_body = {"economicCalendar": [
        {"actual": None, "prev": 1.0, "country": "US", "unit": "%", "estimate": 1.0,
         "event": "Something", "impact": "extremely_important_maybe", "time": "2026-09-15 12:30:00"},
    ]}
    fake_resp = mock_response(200, fake_body)
    with patch.object(calendar_provider._client, "get", new=AsyncMock(return_value=fake_resp)):
        events = await calendar_provider.get_upcoming_events(datetime.now(timezone.utc), datetime.now(timezone.utc) + timedelta(days=2))
    assert events[0].importance == "UNKNOWN"


@pytest.mark.asyncio
async def test_calendar_provider_malformed_timestamp_skips_event_not_fabricated(calendar_provider):
    fake_body = {"economicCalendar": [
        {"actual": None, "prev": 1.0, "country": "US", "estimate": 1.0, "event": "Bad Time Event", "impact": "high", "time": "not-a-real-timestamp"},
        {"actual": None, "prev": 1.0, "country": "US", "estimate": 1.0, "event": "Good Event", "impact": "high", "time": "2026-09-15 12:30:00"},
    ]}
    fake_resp = mock_response(200, fake_body)
    with patch.object(calendar_provider._client, "get", new=AsyncMock(return_value=fake_resp)):
        events = await calendar_provider.get_upcoming_events(datetime.now(timezone.utc), datetime.now(timezone.utc) + timedelta(days=2))
    assert len(events) == 1
    assert events[0].event_name == "Good Event"


@pytest.mark.asyncio
async def test_calendar_provider_derives_event_id_deterministically(calendar_provider):
    fake_body = {"economicCalendar": [
        {"actual": None, "prev": 1.0, "country": "US", "estimate": 1.0, "event": "CPI YoY", "impact": "high", "time": "2026-09-15 12:30:00"},
    ]}
    fake_resp = mock_response(200, fake_body)
    with patch.object(calendar_provider._client, "get", new=AsyncMock(return_value=fake_resp)):
        events1 = await calendar_provider.get_upcoming_events(datetime.now(timezone.utc), datetime.now(timezone.utc) + timedelta(days=2))
        events2 = await calendar_provider.get_upcoming_events(datetime.now(timezone.utc), datetime.now(timezone.utc) + timedelta(days=2))
    assert events1[0].event_id == events2[0].event_id


def test_calendar_api_key_never_in_repr(calendar_provider):
    assert calendar_provider._api_key not in repr(calendar_provider)


@pytest.mark.asyncio
async def test_mock_provider_yields_demo_status(monkeypatch):
    from app.core.config import get_settings
    get_settings.cache_clear()
    monkeypatch.setenv("NEWS_PROVIDER", "mock")
    from app.news_engine.context import get_news_context
    from app.news_engine.models import NEWS_STATUS_DEMO
    context = await get_news_context("EUR/USD")
    assert context.status == NEWS_STATUS_DEMO
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_mock_calendar_yields_none_not_empty_list(monkeypatch):
    from app.core.config import get_settings
    get_settings.cache_clear()
    monkeypatch.setenv("ECONOMIC_CALENDAR_PROVIDER", "mock")
    from app.news_engine.context import get_upcoming_macro_events
    result = await get_upcoming_macro_events()
    assert result is None
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_calendar_provider_deduplicates_by_derived_id(calendar_provider):
    fake_body = {"economicCalendar": [
        {"actual": None, "prev": 1.0, "country": "US", "estimate": 1.0, "event": "CPI YoY", "impact": "high", "time": "2026-09-15 12:30:00"},
        {"actual": None, "prev": 1.0, "country": "US", "estimate": 1.0, "event": "CPI YoY", "impact": "high", "time": "2026-09-15 12:30:00"},
    ]}
    fake_resp = mock_response(200, fake_body)
    with patch.object(calendar_provider._client, "get", new=AsyncMock(return_value=fake_resp)):
        events = await calendar_provider.get_upcoming_events(datetime.now(timezone.utc), datetime.now(timezone.utc) + timedelta(days=2))
    assert len(events) == 1


@pytest.mark.asyncio
async def test_calendar_provider_auth_error(calendar_provider):
    from app.news_engine.providers.finnhub_news import NewsAuthenticationError
    fake_resp = mock_response(401, {"error": "invalid token"})
    with patch.object(calendar_provider._client, "get", new=AsyncMock(return_value=fake_resp)):
        with pytest.raises(NewsAuthenticationError):
            await calendar_provider.get_upcoming_events(datetime.now(timezone.utc), datetime.now(timezone.utc) + timedelta(days=2))


@pytest.mark.asyncio
async def test_calendar_provider_rate_limit(calendar_provider):
    from app.news_engine.providers.finnhub_news import NewsRateLimitError
    fake_resp = mock_response(429, {"error": "rate limited"})
    with patch.object(calendar_provider._client, "get", new=AsyncMock(return_value=fake_resp)):
        with pytest.raises(NewsRateLimitError):
            await calendar_provider.get_upcoming_events(datetime.now(timezone.utc), datetime.now(timezone.utc) + timedelta(days=2))


@pytest.mark.asyncio
async def test_calendar_provider_missing_event_or_time_skipped_not_fabricated(calendar_provider):
    """Data quality: an event missing 'event' or 'time' must be
    skipped, never given a fabricated placeholder value."""
    fake_body = {"economicCalendar": [
        {"actual": None, "prev": 1.0, "country": "US", "estimate": 1.0, "impact": "high", "time": "2026-09-15 12:30:00"},  # missing 'event'
        {"actual": None, "prev": 1.0, "country": "US", "estimate": 1.0, "event": "No Time Event", "impact": "high"},  # missing 'time'
        {"actual": None, "prev": 1.0, "country": "US", "estimate": 1.0, "event": "Valid Event", "impact": "high", "time": "2026-09-15 12:30:00"},
    ]}
    fake_resp = mock_response(200, fake_body)
    with patch.object(calendar_provider._client, "get", new=AsyncMock(return_value=fake_resp)):
        events = await calendar_provider.get_upcoming_events(datetime.now(timezone.utc), datetime.now(timezone.utc) + timedelta(days=2))
    assert len(events) == 1
    assert events[0].event_name == "Valid Event"


def test_news_context_confirmed_no_relevant_news_distinct_from_unavailable():
    """Structural proof these are genuinely different states, not
    just different string labels for the same thing."""
    from app.news_engine.models import NEWS_STATUS_CONFIRMED_NO_RELEVANT_NEWS, NEWS_STATUS_UNAVAILABLE
    assert NEWS_STATUS_CONFIRMED_NO_RELEVANT_NEWS != NEWS_STATUS_UNAVAILABLE


@pytest.mark.asyncio
async def test_live_fetch_with_zero_relevant_items_is_confirmed_no_news_not_unavailable(monkeypatch):
    """A genuine successful fetch that finds nothing relevant for a
    specific instrument must be CONFIRMED_NO_RELEVANT_NEWS, never UNAVAILABLE."""
    from app.core.config import get_settings
    get_settings.cache_clear()
    monkeypatch.setenv("NEWS_PROVIDER", "finnhub")
    monkeypatch.setenv("NEWS_API_KEY", "fake_test_key_never_real")

    import app.news_engine.context as context_module
    context_module._news_cache._store.clear()

    from app.news_engine.models import NewsItem, NEWS_STATUS_CONFIRMED_NO_RELEVANT_NEWS

    irrelevant_item = NewsItem(
        news_id="1", timestamp=datetime.now(timezone.utc), headline="Local bakery wins award",
        summary=None, source="x", url=None, category="forex", relevant_instruments=(), sentiment=None, provider="finnhub",
    )

    with patch("app.news_engine.context.get_news_provider") as mock_get_provider:
        mock_provider = AsyncMock()
        mock_provider.get_recent_news = AsyncMock(return_value=[irrelevant_item])
        mock_get_provider.return_value = mock_provider

        from app.news_engine.context import get_news_context
        result = await get_news_context(instrument="EUR/USD")

    assert result.status == NEWS_STATUS_CONFIRMED_NO_RELEVANT_NEWS
    get_settings.cache_clear()
    context_module._news_cache._store.clear()


@pytest.mark.asyncio
async def test_provider_failure_yields_unavailable_not_confirmed_no_news(monkeypatch):
    from app.core.config import get_settings
    get_settings.cache_clear()
    monkeypatch.setenv("NEWS_PROVIDER", "finnhub")
    monkeypatch.setenv("NEWS_API_KEY", "fake_test_key_never_real")

    import app.news_engine.context as context_module
    context_module._news_cache._store.clear()

    from app.news_engine.models import NEWS_STATUS_UNAVAILABLE

    with patch("app.news_engine.context.get_news_provider") as mock_get_provider:
        mock_provider = AsyncMock()
        mock_provider.get_recent_news = AsyncMock(side_effect=RuntimeError("network down"))
        mock_get_provider.return_value = mock_provider

        from app.news_engine.context import get_news_context
        result = await get_news_context(instrument="EUR/USD")

    assert result.status == NEWS_STATUS_UNAVAILABLE
    assert result.error is not None
    get_settings.cache_clear()
    context_module._news_cache._store.clear()


# ---- Investigation: why /calendar returns UNAVAILABLE in production ----

@pytest.mark.asyncio
async def test_calendar_provider_left_as_mock_returns_none_even_if_key_is_set(monkeypatch):
    """Root cause hypothesis #1: ECONOMIC_CALENDAR_PROVIDER is a
    SEPARATE setting from NEWS_PROVIDER. Getting news working does
    NOT automatically configure calendar -- confirmed here directly:
    even with a real-looking key present, provider='mock' (the
    default) means the calendar is never actually queried."""
    from app.core.config import get_settings
    get_settings.cache_clear()
    monkeypatch.setenv("ECONOMIC_CALENDAR_PROVIDER", "mock")
    monkeypatch.setenv("ECONOMIC_CALENDAR_API_KEY", "a_real_looking_key_here")
    from app.news_engine.context import get_upcoming_macro_events
    result = await get_upcoming_macro_events()
    assert result is None
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_calendar_provider_finnhub_but_missing_key_yields_unavailable_with_logged_error(monkeypatch, caplog):
    """Root cause hypothesis #2: ECONOMIC_CALENDAR_API_KEY is a
    SEPARATE variable from NEWS_API_KEY. Setting the provider name
    alone is not enough."""
    from app.core.config import get_settings
    get_settings.cache_clear()
    monkeypatch.setenv("ECONOMIC_CALENDAR_PROVIDER", "finnhub")
    monkeypatch.delenv("ECONOMIC_CALENDAR_API_KEY", raising=False)

    import app.news_engine.context as context_module
    context_module._calendar_cache._store.clear()

    from app.news_engine.context import get_upcoming_macro_events
    import logging
    with caplog.at_level(logging.WARNING):
        result = await get_upcoming_macro_events()
    assert result is None
    # The fix: this failure must now be LOGGED, not silently swallowed.
    assert any("calendar" in r.message.lower() for r in caplog.records)
    get_settings.cache_clear()
    context_module._calendar_cache._store.clear()


@pytest.mark.asyncio
async def test_calendar_fetch_failure_is_logged_with_key_redacted(monkeypatch, caplog):
    """Any real failure (auth/endpoint/parsing) must be logged for
    diagnosis -- and must NEVER include the raw key in the log line."""
    from app.core.config import get_settings
    get_settings.cache_clear()
    monkeypatch.setenv("ECONOMIC_CALENDAR_PROVIDER", "finnhub")
    monkeypatch.setenv("ECONOMIC_CALENDAR_API_KEY", "super_secret_test_key_123")

    import app.news_engine.context as context_module
    context_module._calendar_cache._store.clear()

    from app.news_engine.providers.finnhub_calendar import FinnhubEconomicCalendarProvider

    with patch("app.news_engine.context.get_economic_calendar_provider") as mock_get_provider:
        mock_provider = AsyncMock()
        mock_provider.get_upcoming_events = AsyncMock(side_effect=RuntimeError("simulated failure containing super_secret_test_key_123"))
        mock_get_provider.return_value = mock_provider

        from app.news_engine.context import get_upcoming_macro_events
        import logging
        with caplog.at_level(logging.WARNING):
            result = await get_upcoming_macro_events()

    assert result is None
    log_text = " ".join(r.message for r in caplog.records)
    assert "super_secret_test_key_123" not in log_text
    assert "[REDACTED]" in log_text or "calendar" in log_text.lower()
    get_settings.cache_clear()
    context_module._calendar_cache._store.clear()


@pytest.mark.asyncio
async def test_calendar_provider_handles_plain_list_response_shape(calendar_provider):
    """Defensive robustness: Finnhub's exact response envelope for this
    specific endpoint was not confirmed with 100% certainty (see
    finnhub_calendar.py's own docstring) -- this proves both the
    wrapped {"economicCalendar": [...]} shape AND a plain top-level
    list [...] are handled correctly, whichever the real API returns."""
    fake_body = [
        {"actual": None, "prev": 1.0, "country": "US", "estimate": 1.0, "event": "CPI YoY", "impact": "high", "time": "2026-09-15 12:30:00"},
    ]
    fake_resp = mock_response(200, fake_body)
    with patch.object(calendar_provider._client, "get", new=AsyncMock(return_value=fake_resp)):
        events = await calendar_provider.get_upcoming_events(datetime.now(timezone.utc), datetime.now(timezone.utc) + timedelta(days=2))
    assert len(events) == 1
    assert events[0].event_name == "CPI YoY"
