"""Phone alert (Web Push) endpoints. Subscriptions hold no account credentials."""

import time

from fastapi import APIRouter, HTTPException

from app.alerts import service
from app.alerts.webpush import validate_subscription

router = APIRouter(prefix="/alerts", tags=["alerts"])

_last_test: dict[str, float] = {}
TEST_COOLDOWN_SECONDS = 20


def _subscription_from(payload: dict):
    keys = payload.get("keys") or {}
    try:
        return validate_subscription(
            str(payload.get("endpoint", "")), str(keys.get("p256dh", "")), str(keys.get("auth", ""))
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/public-key")
async def alerts_public_key() -> dict:
    from app.alerts.store import public_key

    try:
        return {"public_key": await public_key()}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Alerts are unavailable: {exc}") from exc


@router.post("/subscribe")
async def alerts_subscribe(payload: dict) -> dict:
    from app.alerts.store import save_subscription

    sub = _subscription_from(payload)
    try:
        await save_subscription(sub)
    except ValueError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    return {"status": "SUBSCRIBED", **service.next_schedule()}


@router.post("/unsubscribe")
async def alerts_unsubscribe(payload: dict) -> dict:
    from app.alerts.store import remove_subscription

    endpoint = str(payload.get("endpoint", ""))
    if endpoint:
        await remove_subscription(endpoint)
    return {"status": "UNSUBSCRIBED"}


@router.post("/test")
async def alerts_test(payload: dict) -> dict:
    """Send a test notification to the caller's own browser only."""
    from app.alerts.store import has_subscription, send_alert

    endpoint = str(payload.get("endpoint", ""))
    if not endpoint or not await has_subscription(endpoint):
        raise HTTPException(status_code=404, detail="This browser is not subscribed to alerts.")
    now = time.monotonic()
    if now - _last_test.get(endpoint, 0.0) < TEST_COOLDOWN_SECONDS:
        raise HTTPException(status_code=429, detail="Please wait a few seconds before sending another test.")
    _last_test[endpoint] = now
    result = await send_alert(
        {
            "title": "Tembo alerts are on",
            "body": "You'll get a heads-up about 5 minutes before a signal can confirm, then the result when the candle closes.",
            "tag": "tembo-test",
            "url": "/#/live",
            "kind": "test",
        },
        endpoint=endpoint,
    )
    if result["sent"] == 0:
        raise HTTPException(status_code=502, detail=f"The push service did not accept the test ({result}).")
    return {"status": "SENT", **result}


@router.get("/status")
async def alerts_status() -> dict:
    from app.alerts.store import subscription_count
    from app.core.config import get_settings

    try:
        count = await subscription_count()
    except Exception:
        count = None
    return {
        "enabled": get_settings().enable_alerts,
        "subscriptions": count,
        "instruments": list(service.ALERT_INSTRUMENTS),
        "timeframe": service.TIMEFRAME,
        **service.next_schedule(),
        "recent": list(service.recent_alerts)[:10],
        "loop": dict(service.loop_status),
    }
