"""Deriv demo execution endpoints for the Tembo cockpit.

All execution routes are hard-locked to the configured Deriv demo account.
They never connect to a real-money account.
"""

import base64
import hashlib
import hmac
import json
import time

from fastapi import APIRouter, HTTPException

from app.core.config import get_settings
from app.api.routes.live import live_decision
from app.data_engine.providers.deriv import DerivMarketDataProvider
from app.integrations.deriv import (
    DerivAPIError,
    DerivConfigurationError,
    DerivDemoClient,
)

router = APIRouter(prefix="/deriv", tags=["deriv"])

def _sign_demo_authorization(*, proposal_id: str, price: float, instrument: str, direction: str) -> str:
    settings = get_settings()
    if not settings.deriv_api_token:
        raise DerivConfigurationError("Deriv demo credentials are not configured.")
    payload = {
        "proposal_id": proposal_id,
        "price": round(price, 8),
        "instrument": instrument,
        "direction": direction,
        "expires_at": int(time.time()) + 120,
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    body = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    signature = hmac.new(settings.deriv_api_token.encode(), body.encode(), hashlib.sha256).hexdigest()
    return body + "." + signature


def _verify_demo_authorization(token: str, *, proposal_id: str, price: float) -> None:
    settings = get_settings()
    try:
        body, signature = token.split(".", 1)
        expected = hmac.new(settings.deriv_api_token.encode(), body.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError("invalid signature")
        raw = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))
        payload = json.loads(raw.decode())
        if int(payload["expires_at"]) < int(time.time()):
            raise ValueError("authorization expired")
        if payload["proposal_id"] != proposal_id or abs(float(payload["price"]) - price) > 1e-8:
            raise ValueError("proposal mismatch")
    except (ValueError, KeyError, TypeError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise DerivAPIError("Demo execution authorization is invalid or expired.") from exc



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
        decision = await live_decision(instrument=instrument, timeframe=str(payload.get("timeframe", "h1")))
        if not decision.get("paper_eligibility", {}).get("eligible"):
            raise DerivAPIError("Tembo execution gate rejected the setup: " + str(decision.get("paper_eligibility", {}).get("reason", "not eligible")))
        if decision.get("decision") != direction:
            raise DerivAPIError("Requested direction does not match Tembo's current live decision.")
        result = await DerivDemoClient().proposal(
            instrument=instrument,
            direction=direction,
            stake=stake,
            multiplier=multiplier,
        )
        result["execution_token"] = _sign_demo_authorization(
            proposal_id=str(result["proposal_id"]),
            price=float(result["ask_price"]),
            instrument=instrument,
            direction=direction,
        )
        return result
    except (DerivConfigurationError, DerivAPIError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/demo/buy")
async def deriv_demo_buy(payload: dict) -> dict:
    try:
        proposal_id = str(payload.get("proposal_id", "")).strip()
        price = float(payload.get("price", 0))
        token = str(payload.get("execution_token", "")).strip()
        _verify_demo_authorization(token, proposal_id=proposal_id, price=price)
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
