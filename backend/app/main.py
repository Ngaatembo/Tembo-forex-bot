"""
Application entrypoint.

Run with:
    uvicorn app.main:app --reload
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import admin_data, backtest, decisions, health, market_data, markets, news, paper_trading, research, strategy, technical_analysis
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.database.init import initialize_database

settings = get_settings()
configure_logging("DEBUG" if settings.debug else "INFO")


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Bootstrap the foundational Render PostgreSQL schema before serving API
    # traffic. create_all is idempotent and never removes existing data.
    await initialize_database()
    yield


app = FastAPI(
    title=settings.app_name,
    description=(
        "Modular research platform for forex market analysis, backtesting, "
        "and paper trading. Not an autonomous trading system. See README.md."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# CORS: allows the deployed frontend to call this API from the browser.
# This is not an authentication mechanism and no API credentials live here.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_allowed_origins.split(",") if o.strip()],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(health.router, tags=["system"])
app.include_router(market_data.router)
app.include_router(markets.router)
app.include_router(technical_analysis.router)
app.include_router(strategy.router)
app.include_router(backtest.router)
app.include_router(research.router)
app.include_router(decisions.router)
app.include_router(paper_trading.router)
app.include_router(news.router)
app.include_router(admin_data.router)


@app.get("/")
async def root() -> dict:
    return {
        "name": settings.app_name,
        "phase": "Phase 0 — architecture skeleton",
        "live_execution_enabled": settings.enable_live_execution,
    }
