"""Persistence and delivery for Web Push alerts."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

from app.alerts.webpush import (
    Subscription,
    application_server_key,
    build_push_request,
    generate_vapid_private_key_pem,
)
from app.core.config import get_settings
from app.database.models import AppSetting, PushSubscription
from app.database.session import AsyncSessionLocal

logger = logging.getLogger(__name__)

VAPID_SETTING_KEY = "webpush_vapid_private_key_pem"
MAX_SUBSCRIPTIONS = 50
MAX_FAILURES = 5

_cached_private_pem: str | None = None


async def vapid_private_pem() -> str:
    """Load the VAPID key, generating and storing it once on first use."""
    global _cached_private_pem
    if _cached_private_pem:
        return _cached_private_pem
    async with AsyncSessionLocal() as db:
        row = await db.get(AppSetting, VAPID_SETTING_KEY)
        if row is None:
            await db.execute(
                insert(AppSetting)
                .values(key=VAPID_SETTING_KEY, value=generate_vapid_private_key_pem())
                .on_conflict_do_nothing(index_elements=["key"])
            )
            await db.commit()
            row = await db.get(AppSetting, VAPID_SETTING_KEY)
        _cached_private_pem = row.value
        return row.value


async def public_key() -> str:
    return application_server_key(await vapid_private_pem())


async def save_subscription(sub: Subscription) -> None:
    async with AsyncSessionLocal() as db:
        existing = (await db.execute(
            select(PushSubscription).where(PushSubscription.endpoint == sub.endpoint)
        )).scalar_one_or_none()
        if existing is not None:
            existing.p256dh = sub.p256dh
            existing.auth = sub.auth
            existing.failure_count = 0
        else:
            count = len((await db.execute(select(PushSubscription.id))).scalars().all())
            if count >= MAX_SUBSCRIPTIONS:
                raise ValueError("Too many alert subscriptions on this server.")
            db.add(PushSubscription(endpoint=sub.endpoint, p256dh=sub.p256dh, auth=sub.auth))
        await db.commit()


async def remove_subscription(endpoint: str) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(delete(PushSubscription).where(PushSubscription.endpoint == endpoint))
        await db.commit()


async def subscription_count() -> int:
    async with AsyncSessionLocal() as db:
        return len((await db.execute(select(PushSubscription.id))).scalars().all())


async def has_subscription(endpoint: str) -> bool:
    async with AsyncSessionLocal() as db:
        row = (await db.execute(
            select(PushSubscription.id).where(PushSubscription.endpoint == endpoint)
        )).scalar_one_or_none()
        return row is not None


async def send_alert(payload: dict, *, endpoint: str | None = None) -> dict:
    """Send one notification to every subscribed browser (or just `endpoint`)."""
    pem = await vapid_private_pem()
    subject = get_settings().alerts_vapid_subject
    async with AsyncSessionLocal() as db:
        query = select(PushSubscription)
        if endpoint is not None:
            query = query.where(PushSubscription.endpoint == endpoint)
        rows = (await db.execute(query)).scalars().all()

        sent = failed = removed = 0
        async with httpx.AsyncClient(timeout=15.0) as client:
            for row in rows:
                sub = Subscription(row.endpoint, row.p256dh, row.auth)
                try:
                    headers, body = build_push_request(sub, payload, pem, subject)
                    response = await client.post(sub.endpoint, headers=headers, content=body)
                except Exception as exc:  # network errors must never stop the alert loop
                    logger.warning("Push delivery failed: %s", exc)
                    row.failure_count += 1
                    failed += 1
                    continue
                if response.status_code in (404, 410):
                    await db.delete(row)  # browser unsubscribed or expired
                    removed += 1
                elif response.status_code >= 400:
                    logger.warning("Push service returned %s: %s", response.status_code, response.text[:200])
                    row.failure_count += 1
                    failed += 1
                    if row.failure_count >= MAX_FAILURES:
                        await db.delete(row)
                        removed += 1
                else:
                    row.failure_count = 0
                    row.last_success_at = datetime.now(timezone.utc)
                    sent += 1
        await db.commit()
    return {"sent": sent, "failed": failed, "removed": removed}
