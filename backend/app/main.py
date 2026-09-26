"""
Application entrypoint.

Run with:
    uvicorn app.main:app --reload
"""

from contextlib import asynccontextmanager
import logging
import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import admin_data, backtest, decisions, health, market_data, markets, news, paper_trading, research, strategy, technical_analysis
from app.api.routes.live import router as live_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.database.init import initialize_database
from app.database.session import AsyncSessionLocal
from app.paper_trading.runtime import run_paper_cycle

settings = get_settings()
configure_logging("DEBUG" if settings.debug else "INFO")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Bootstrap the foundational Render PostgreSQL schema when a database is
    # configured. A database outage must not prevent the read-only dashboard
    # from starting; /health reports database availability separately.
    try:
        await initialize_database()
        logger.info("Database schema initialization/check completed.")
    except Exception:
        logger.exception("Database schema initialization failed; starting API in degraded database mode.")
    paper_task = None
    if settings.enable_paper_runtime:
        async def _paper_loop():
            while True:
                try:
                    async with AsyncSessionLocal() as session:
                        await run_paper_cycle(session)
                        logger.info("Paper runtime cycle completed.")
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("Paper runtime cycle failed; no broker action was attempted.")
                await asyncio.sleep(max(60, settings.paper_runtime_interval_seconds))

        paper_task = asyncio.create_task(_paper_loop())
        logger.info("Paper runtime enabled: interval=%ss; execution remains disabled.", max(60, settings.paper_runtime_interval_seconds))
    try:
        yield
    finally:
        if paper_task is not None:
            paper_task.cancel()
            try:
                await paper_task
            except asyncio.CancelledError:
                pass


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
app.include_router(live_router)
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
        "phase": "Persistent paper-runtime stage",
        "live_execution_enabled": settings.enable_live_execution,
    }
