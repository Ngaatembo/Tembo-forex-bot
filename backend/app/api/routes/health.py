"""
GET /health

Reports whether each core dependency is reachable.

market_data now distinguishes four real states, not just two:
  "mock"          -- MARKET_DATA_PROVIDER=mock, no real provider in use
  "configured"    -- a real provider name + API key are both present,
                     but a live connectivity check has not completed
                     yet (e.g. right after startup)
  "available"     -- a live connectivity check to the provider
                     actually succeeded recently
  "unavailable"   -- either credentials are missing/invalid for a
                     real provider name, or a live check was
                     attempted and failed

WHY THE LIVE CHECK NEVER BLOCKS THIS REQUEST: /health is polled
frequently by the hosting platform itself (e.g. Render's own health
checks), and a health endpoint that blocks on an external network call
is bad practice regardless. When no cached result exists yet, this
endpoint kicks off a real check in the background (fire-and-forget)
and reports "configured" for THIS request — the next poll, once the
background check has completed, reports the genuine "available"/
"unavailable" result. The cache TTL below also means Twelve Data
itself is only actually called periodically, not on every poll.
"""

import asyncio
import time

from fastapi import APIRouter

from app.core.config import get_settings
from app.database.session import check_database_health

router = APIRouter()

_CONNECTIVITY_CACHE_TTL_SECONDS = 300  # 5 minutes
_connectivity_cache: dict[str, tuple[float, bool]] = {}  # provider_name -> (checked_at, is_available)
_check_in_progress: set[str] = set()


async def _run_connectivity_check(provider_name: str) -> None:
    from app.data_engine.market_data import get_market_data_provider

    is_available = False
    try:
        provider = get_market_data_provider(provider_name)
        await provider.get_current_price("EUR/USD")
        is_available = True
    except Exception:
        is_available = False
    finally:
        _connectivity_cache[provider_name] = (time.monotonic(), is_available)
        _check_in_progress.discard(provider_name)


def _market_data_status(provider_name: str) -> str:
    now = time.monotonic()
    cached = _connectivity_cache.get(provider_name)

    if cached is not None and (now - cached[0]) < _CONNECTIVITY_CACHE_TTL_SECONDS:
        return "available" if cached[1] else "unavailable"

    # No fresh cached result -- kick off a real check in the background
    # (never awaited here, so this request never blocks on it) and
    # report the honest "not yet verified" state for this request.
    if provider_name not in _check_in_progress:
        _check_in_progress.add(provider_name)
        asyncio.create_task(_run_connectivity_check(provider_name))
    return "configured"


@router.get("/health")
async def health_check() -> dict:
    settings = get_settings()
    db_ok = await check_database_health()

    if settings.market_data_provider == "mock":
        market_data_status = "mock"
    elif not settings.market_data_api_key:
        market_data_status = "unavailable"
    else:
        market_data_status = _market_data_status(settings.market_data_provider)

    return {
        "status": "ok" if db_ok else "degraded",
        "database": "available" if db_ok else "unavailable",
        "market_data": market_data_status,
        "news_service": "not_configured" if settings.news_provider == "mock" else "configured",
        "ai_service": "configured" if settings.ai_api_key else "not_configured",
        "paper_broker": "available",
        "live_execution_enabled": settings.enable_live_execution,
    }
