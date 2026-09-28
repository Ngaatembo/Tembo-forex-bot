"""Deriv connection telemetry for the Tembo cockpit.

This route never places, modifies, or closes a contract. It verifies the
server-side credentials and reads the demo account balance/portfolio.
"""

from fastapi import APIRouter, HTTPException

from app.core.config import get_settings
from app.data_engine.providers.deriv import DerivMarketDataProvider
from app.integrations.deriv import (
    DerivAPIError,
    DerivConfigurationError,
    DerivDemoClient,
)

router = APIRouter(prefix="/deriv", tags=["deriv"])


@router.get("/status")
async def deriv_status() -> dict:
    settings = get_settings()
    configured = bool(settings.deriv_api_token and settings.deriv_account_id)

    if not configured:
        return {
            "connected": False,
            "configured": False,
            "mode": "demo",
            "account_id": None,
            "message": (
                "Deriv demo credentials are not configured on the server. "
                "Market-data access can remain public/read-only."
            ),
        }

    try:
        return await DerivDemoClient().account_status()
    except DerivConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except DerivAPIError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Deriv demo connection failed: {exc}",
        ) from exc


@router.get("/markets")
async def deriv_markets() -> dict:
    try:
        symbols = await DerivMarketDataProvider().get_active_markets()
        return {"status": "AVAILABLE", "symbols": symbols}
    except (DerivConfigurationError, DerivAPIError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
