"""
GET /health

Reports whether each core dependency is reachable. Phase 0 stubs
market data / news / AI / paper broker as "not_configured" rather
than probing them, since no real providers are wired in yet.
"""

from fastapi import APIRouter

from app.core.config import get_settings
from app.database.session import check_database_health

router = APIRouter()


@router.get("/health")
async def health_check() -> dict:
    settings = get_settings()
    db_ok = await check_database_health()

    return {
        "status": "ok" if db_ok else "degraded",
        "database": "available" if db_ok else "unavailable",
        "market_data": "not_configured" if settings.market_data_provider == "mock" else "configured",
        "news_service": "not_configured" if settings.news_provider == "mock" else "configured",
        "ai_service": "configured" if settings.ai_api_key else "not_configured",
        "paper_broker": "available",
        "live_execution_enabled": settings.enable_live_execution,
    }
