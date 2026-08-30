"""
Application entrypoint.

Run with:
    uvicorn app.main:app --reload
"""

from fastapi import FastAPI

from app.api.routes import health, market_data, technical_analysis
from app.core.config import get_settings
from app.core.logging import configure_logging

settings = get_settings()
configure_logging("DEBUG" if settings.debug else "INFO")

app = FastAPI(
    title=settings.app_name,
    description=(
        "Modular research platform for forex market analysis, backtesting, "
        "and paper trading. Not an autonomous trading system. See README.md."
    ),
    version="0.1.0",
)

app.include_router(health.router, tags=["system"])
app.include_router(market_data.router)
app.include_router(technical_analysis.router)


@app.get("/")
async def root() -> dict:
    return {
        "name": settings.app_name,
        "phase": "Phase 0 — architecture skeleton",
        "live_execution_enabled": settings.enable_live_execution,
    }
