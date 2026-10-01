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

def _order_fields(*, instrument: str, direction: str, stake: float, multiplier: float, price: float) -> dict:
    return {
        "instrument": instrument,
        "direction": direction,
        "stake": round(float(stake), 2),
        "multiplier": round(float(multiplier), 4),
        "price": round(float(price), 2),
    }


def _sign_demo_authorization(*, instrument: str, direction: str, stake: float, multiplier: float, price: float) -> str:
    """Sign the exact order the user was shown, valid for 120 seconds.

    The token binds the order (market, side, stake, multiplier, price), not a
    Deriv proposal id: a proposal id only works on the connection that created
    it, so the buy re-prices and buys on one fresh connection instead.
    """
    settings = get_settings()
    if not settings.deriv_api_token:
        raise DerivConfigurationError("Deriv demo credentials are not configured.")
    payload = {
        **_order_fields(instrument=instrument, direction=direction, stake=stake, multiplier=multiplier, price=price),
        "expires_at": int(time.time()) + 120,
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    body = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    signature = hmac.new(settings.deriv_api_token.encode(), body.encode(), hashlib.sha256).hexdigest()
    return body + "." + signature


def _verify_demo_authorization(token: str) -> dict:
    """Return the signed order, or raise if the token is forged or expired."""
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
        return _order_fields(
            instrument=str(payload["instrument"]),
            direction=str(payload["direction"]),
            stake=float(payload["stake"]),
            multiplier=float(payload["multiplier"]),
            price=float(payload["price"]),
        )
    except (ValueError, KeyError, TypeError, AttributeError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise DerivAPIError("Demo execution authorization is invalid or expired. Get a fresh quote and confirm again.") from exc


async def _checked_decision(instrument: str, direction: str, timeframe: str = "h1") -> dict:
    """Re-run Tembo's live decision and require it to still allow this exact trade."""
    decision = await live_decision(instrument=instrument, timeframe=timeframe)
    if not decision.get("paper_eligibility", {}).get("eligible"):
        raise DerivAPIError("Tembo execution gate rejected the setup: " + str(decision.get("paper_eligibility", {}).get("reason", "not eligible")))
    if decision.get("decision") != direction:
        raise DerivAPIError("Requested direction does not match Tembo's current live decision.")
    return decision


def _plan_levels(decision: dict) -> dict:
    plan = decision.get("trade_plan") or {}
    return {
        key: float(plan[key]) if plan.get(key) is not None else None
        for key in ("entry", "stop_loss", "take_profit")
    }



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
        multiplier = float(payload.get("multiplier", 100))
        decision = await _checked_decision(instrument, direction, str(payload.get("timeframe", "h1")))
        result = await DerivDemoClient().proposal(
            instrument=instrument,
            direction=direction,
            stake=stake,
            multiplier=multiplier,
            **_plan_levels(decision),
        )
        # Sign what the user is about to confirm (Deriv may have adjusted the
        # multiplier to one it accepts for this market).
        result["execution_token"] = _sign_demo_authorization(
            instrument=instrument,
            direction=direction,
            stake=float(result["stake"]),
            multiplier=float(result["multiplier"]),
            price=float(result["ask_price"]),
        )
        return result
    except (DerivConfigurationError, DerivAPIError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/demo/buy")
async def deriv_demo_buy(payload: dict) -> dict:
    """Buy the order the user confirmed: re-check Tembo, then quote + buy on one connection."""
    try:
        order = _verify_demo_authorization(str(payload.get("execution_token", "")).strip())
        decision = await _checked_decision(order["instrument"], order["direction"], str(payload.get("timeframe", "h1")))
        return await DerivDemoClient().quote_and_buy_demo(
            instrument=order["instrument"],
            direction=order["direction"],
            stake=order["stake"],
            multiplier=order["multiplier"],
            max_price=order["price"],
            **_plan_levels(decision),
        )
    except (DerivConfigurationError, DerivAPIError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/demo/contract")
async def deriv_demo_contract(contract_id: int) -> dict:
    try:
        client = DerivDemoClient()
        current = await client.open_contract(contract_id)
        balance = await client.account_balance()
        contract = current.get("contract") or {}
        return {
            **current,
            "account_balance": balance.get("balance"),
            "currency": balance.get("currency") or contract.get("currency") or "USD",
            "broker_confirmed": True,
            "contract_id": contract.get("contract_id", contract_id),
        }
    except (DerivConfigurationError, DerivAPIError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/demo/contract/history")
async def deriv_demo_contract_history(contract_id: int) -> dict:
    try:
        return await DerivDemoClient().contract_update_history(contract_id)
    except (DerivConfigurationError, DerivAPIError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/demo/contract/update")
async def deriv_demo_contract_update(payload: dict) -> dict:
    try:
        contract_id = int(payload.get("contract_id"))
        stop_loss = payload.get("stop_loss")
        take_profit = payload.get("take_profit")
        # Fail closed: only the configured demo account may be touched.
        client = DerivDemoClient()
        current = await client.open_contract(contract_id)
        contract = current.get("contract") or {}
        if str(contract.get("is_sold", "0")).lower() in {"1", "true"} or str(contract.get("status", "")).lower() in {"sold", "closed", "expired"}:
            raise DerivAPIError("Cannot update protection on a closed demo contract.")
        return await client.update_contract_protection(
            contract_id=contract_id,
            stop_loss=float(stop_loss) if stop_loss is not None else None,
            take_profit=float(take_profit) if take_profit is not None else None,
        )
    except (DerivConfigurationError, DerivAPIError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/demo/sell")
async def deriv_demo_sell(payload: dict) -> dict:
    try:
        contract_id = int(payload.get("contract_id"))
        return await DerivDemoClient().sell_demo(contract_id)
    except (DerivConfigurationError, DerivAPIError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Demo connection test
# ---------------------------------------------------------------------------
# Proves the whole demo execution path works (login -> quote with SL/TP ->
# buy -> read contract -> close) BEFORE the first real Tembo signal arrives.
# It is NOT a trading decision: fixed $1 demo stake, closed within seconds,
# demo account only (DerivDemoClient refuses anything else), rate-limited.

SELFTEST_STAKE = 1.0
SELFTEST_MULTIPLIERS = (100,)  # Deriv's error lists the accepted values; the client adapts
SELFTEST_COOLDOWN_SECONDS = 120
_last_selftest = {"at": 0.0}


@router.post("/demo/selftest")
async def deriv_demo_selftest(payload: dict | None = None) -> dict:
    import asyncio

    from app.api.routes.live import INSTRUMENTS
    from app.data_engine.market_data import get_market_data_provider

    instrument = str((payload or {}).get("instrument") or "USD/JPY").strip()
    if instrument not in INSTRUMENTS:
        raise HTTPException(status_code=400, detail=f"Connection test supports {', '.join(INSTRUMENTS)}.")
    now = time.time()
    wait = SELFTEST_COOLDOWN_SECONDS - (now - _last_selftest["at"])
    if wait > 0:
        raise HTTPException(status_code=429, detail=f"Please wait {int(wait)} seconds before running another connection test.")
    _last_selftest["at"] = now

    steps: list[dict] = []

    def step(name: str, ok: bool, detail: str) -> None:
        steps.append({"step": name, "ok": ok, "detail": detail})

    try:
        client = DerivDemoClient()
        status = await client.account_status()
        step("Log in to Deriv demo", True, f"{status.get('account_id')} · balance {status.get('balance')} {status.get('currency') or ''}".strip())
    except (DerivConfigurationError, DerivAPIError) as exc:
        step("Log in to Deriv demo", False, str(exc))
        return {"status": "FAILED", "instrument": instrument, "steps": steps}

    try:
        price = float(await get_market_data_provider(get_settings().market_data_provider, instrument).get_current_price(instrument))
    except Exception as exc:
        step("Get live price", False, str(exc))
        return {"status": "FAILED", "instrument": instrument, "steps": steps}
    step("Get live price", True, f"{instrument} {price}")

    # The quote and the buy must share one Deriv connection: a proposal id is
    # unknown on any other connection.
    proposal = None
    bought = None
    errors = []
    try:
        async with client.session():
            for multiplier in SELFTEST_MULTIPLIERS:
                try:
                    proposal = await client.proposal(
                        instrument=instrument, direction="BUY", stake=SELFTEST_STAKE, multiplier=multiplier,
                        entry=price, stop_loss=price * 0.995, take_profit=price * 1.005,
                    )
                    break
                except DerivAPIError as exc:
                    errors.append(f"x{multiplier}: {exc}")
                    if "multiplier" not in str(exc).lower():
                        break
            if proposal is None:
                step("Get a quote with stop loss / take profit", False, " | ".join(errors))
                return {"status": "FAILED", "instrument": instrument, "steps": steps}
            step(
                "Get a quote with stop loss / take profit", True,
                f"x{proposal['multiplier']:g}, stake {proposal['ask_price']} {proposal['currency']}, "
                f"protection {'attached' if proposal['protection']['attached'] else 'NOT attached'} {proposal['protection']['limit_order']}",
            )
            try:
                bought = await client.buy_demo(proposal_id=str(proposal["proposal_id"]), price=float(proposal["ask_price"]))
            except DerivAPIError as exc:
                step("Open the demo contract", False, str(exc))
                return {"status": "FAILED", "instrument": instrument, "steps": steps}
    except DerivAPIError as exc:
        # The shared connection itself failed (before or after the steps above).
        if bought is None:
            name = "Open the demo contract" if proposal is not None else "Get a quote with stop loss / take profit"
            step(name, False, str(exc))
            return {"status": "FAILED", "instrument": instrument, "steps": steps}
    contract_id = bought["contract_id"]
    step("Open the demo contract", True, f"contract {contract_id} bought for {bought['buy_price']}")

    await asyncio.sleep(3)
    try:
        contract = (await client.open_contract(contract_id)).get("contract") or {}
        step("Read the open contract", True, f"profit {contract.get('profit')} · status {contract.get('status')}")
    except DerivAPIError as exc:
        step("Read the open contract", False, str(exc))

    try:
        sold = await client.sell_demo(contract_id)
        step("Close the demo contract", True, f"sold for {sold.get('sold_for')}")
    except DerivAPIError as exc:
        step("Close the demo contract", False, f"{exc} — close contract {contract_id} manually in Deriv if it is still open.")
        return {"status": "FAILED", "instrument": instrument, "contract_id": contract_id, "steps": steps}

    try:
        after = await client.account_status()
        step("Check balance after", True, f"balance {after.get('balance')} {after.get('currency') or ''} · open contracts {after.get('open_positions')}")
    except DerivAPIError as exc:
        step("Check balance after", False, str(exc))

    ok = all(s["ok"] for s in steps)
    return {"status": "PASSED" if ok else "PARTIAL", "instrument": instrument, "contract_id": contract_id, "steps": steps}
