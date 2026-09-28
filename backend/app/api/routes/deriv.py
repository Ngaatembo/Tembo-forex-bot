"""Deriv demo execution endpoints for the Tembo cockpit.

All execution routes are hard-locked to the configured Deriv demo account.
They never connect to a real-money account.
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


@router.post("/demo/proposal")
async def deriv_demo_proposal(payload: dict) -> dict:
    try:
        instrument = str(payload.get("instrument", "")).strip()
        direction = str(payload.get("direction", "")).strip().upper()
        stake = float(payload.get("stake", 1))
        multiplier = float(payload.get("multiplier", 10))
        return await DerivDemoClient().proposal(
            instrument=instrument,
            direction=direction,
            stake=stake,
            multiplier=multiplier,
        )
    except (DerivConfigurationError, DerivAPIError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/demo/buy")
async def deriv_demo_buy(payload: dict) -> dict:
    try:
        proposal_id = str(payload.get("proposal_id", "")).strip()
        price = float(payload.get("price", 0))
        return await DerivDemoClient().buy_demo(proposal_id=proposal_id, price=price)
    except (DerivConfigurationError, DerivAPIError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/demo/contract")
async def deriv_demo_contract(contract_id: int) -> dict:
    try:
        return await DerivDemoClient().open_contract(contract_id)
    except (DerivConfigurationError, DerivAPIError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/demo/sell")
async def deriv_demo_sell(payload: dict) -> dict:
    try:
        contract_id = int(payload.get("contract_id"))
        return await DerivDemoClient().sell_demo(contract_id)
    except (DerivConfigurationError, DerivAPIError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
