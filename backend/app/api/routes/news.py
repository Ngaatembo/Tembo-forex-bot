"""
GET /news, GET /news/{instrument}, GET /calendar, GET /calendar/{currency},
GET /system/data-status — all read-only, all built on the context
builders in context.py so the UNAVAILABLE/DEMO/STALE/LIVE distinction
is enforced in one place, not reimplemented per route.
"""

from urllib.parse import unquote

from fastapi import APIRouter

from app.core.config import get_settings
from app.news_engine.context import get_news_context, get_upcoming_macro_events, get_last_calendar_error

router = APIRouter(tags=["news"])


def _news_item_to_dict(item) -> dict:
    return {
        "news_id": item.news_id, "timestamp": item.timestamp.isoformat(), "headline": item.headline,
        "summary": item.summary, "source": item.source, "url": item.url, "category": item.category,
        "relevant_instruments": list(item.relevant_instruments), "sentiment": item.sentiment, "provider": item.provider,
    }


def _macro_event_to_dict(event) -> dict:
    return {
        "event_id": event.event_id, "timestamp": event.timestamp.isoformat(), "currency": event.currency,
        "country": event.country, "event_name": event.event_name, "importance": event.importance,
        "previous": event.previous, "forecast": event.forecast, "actual": event.actual,
        "source": event.source, "url": event.url, "time_confirmed": event.time_confirmed,
    }


@router.get("/news")
async def get_news() -> dict:
    context = await get_news_context(instrument=None)
    return {
        "status": context.status, "freshness": context.freshness, "provider": context.provider,
        "last_successful_fetch": context.last_successful_fetch.isoformat() if context.last_successful_fetch else None,
        "error": context.error,
        "items": [_news_item_to_dict(i) for i in context.relevant_news],
    }


@router.get("/news/{instrument:path}")
async def get_news_for_instrument(instrument: str) -> dict:
    instrument = unquote(instrument)
    context = await get_news_context(instrument=instrument)
    return {
        "instrument": instrument, "status": context.status, "freshness": context.freshness,
        "provider": context.provider,
        "last_successful_fetch": context.last_successful_fetch.isoformat() if context.last_successful_fetch else None,
        "error": context.error,
        "items": [_news_item_to_dict(i) for i in context.relevant_news],
    }


def _live_status_label() -> str:
    """LIVE only for a genuinely real-time provider (e.g. Finnhub).
    static_central_banks is a manually verified, attributed static
    dataset -- reporting it as LIVE would misrepresent it, per Phase 1's
    explicit requirement."""
    settings = get_settings()
    if settings.economic_calendar_provider == "static_central_banks":
        return "STATIC_OFFICIAL"
    return "LIVE"


@router.get("/calendar")
async def get_calendar() -> dict:
    # Full-year browsing needs BOTH directions from "now" -- a static
    # dataset's earlier-in-the-year events would otherwise be invisible
    # once "now" has passed them (found as a real bug: forward-only
    # windowing hid 5 of 8 Fed 2026 dates once fetched after September).
    events = await get_upcoming_macro_events(lookahead_hours=24 * 370, lookback_hours=24 * 370)
    if events is None:
        return {"status": "UNAVAILABLE", "events": [], "error": get_last_calendar_error()}
    return {"status": _live_status_label(), "events": [_macro_event_to_dict(e) for e in events], "error": None}


@router.get("/calendar/{currency}")
async def get_calendar_for_currency(currency: str) -> dict:
    currency = currency.upper()
    events = await get_upcoming_macro_events(lookahead_hours=24 * 370, lookback_hours=24 * 370)
    if events is None:
        return {"currency": currency, "status": "UNAVAILABLE", "events": [], "error": get_last_calendar_error()}
    filtered = [e for e in events if e.currency == currency]
    return {"currency": currency, "status": _live_status_label(), "events": [_macro_event_to_dict(e) for e in filtered], "error": None}


@router.get("/system/data-status")
async def get_data_status() -> dict:
    settings = get_settings()
    from app.api.routes.health import _market_data_status

    market_data_status = "mock" if settings.market_data_provider == "mock" else (
        "unavailable" if not settings.market_data_api_key else _market_data_status(settings.market_data_provider)
    )

    news_status = "mock" if settings.news_provider == "mock" else (
        "unavailable" if not settings.news_api_key else "configured"
    )
    calendar_status = "mock" if settings.economic_calendar_provider == "mock" else (
        "unavailable" if not settings.economic_calendar_api_key else "configured"
    )

    return {
        "market_data": {"provider": settings.market_data_provider, "status": market_data_status},
        "news": {"provider": settings.news_provider, "status": news_status},
        "economic_calendar": {"provider": settings.economic_calendar_provider, "status": calendar_status},
    }
