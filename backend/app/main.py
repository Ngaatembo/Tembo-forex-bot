"""
Application entrypoint.

Run with:
    uvicorn app.main:app --reload
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import backtest, decisions, health, market_data, paper_trading, research, strategy, technical_analysis
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

# CORS: allows the frontend (a different origin -- e.g. Vercel) to call
# this API from the browser. This is NOT a secret or an auth mechanism --
# it never exposes credentials, it only controls which origins the
# browser permits to read responses. No API key of any kind lives here.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_allowed_origins.split(",") if o.strip()],
    allow_credentials=False,
    allow_methods=["GET"],  # every route in this API is GET-only -- see the security-boundary tests
    allow_headers=["*"],
)

app.include_router(health.router, tags=["system"])
app.include_router(market_data.router)
app.include_router(technical_analysis.router)
app.include_router(strategy.router)
app.include_router(backtest.router)
app.include_router(research.router)
app.include_router(decisions.router)
app.include_router(paper_trading.router)


@app.get("/")
async def root() -> dict:
    return {
        "name": settings.app_name,
        "phase": "Phase 0 — architecture skeleton",
        "live_execution_enabled": settings.enable_live_execution,
    }
