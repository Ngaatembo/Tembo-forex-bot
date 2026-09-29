"""Phone alerts: Web Push crypto, subscription validation, schedule and heads-up logic."""

import hashlib
import hmac
import json
import os
import struct
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.alerts import service
from app.alerts.webpush import (
    b64url_decode,
    b64url_encode,
    encrypt_payload,
    generate_vapid_private_key_pem,
    public_key_bytes,
    vapid_authorization,
    validate_subscription,
)
from app.data_engine.market_data import Candle


def _h(key, data):
    return hmac.new(key, data, hashlib.sha256).digest()


def _ua_decrypt(body: bytes, ua_private, auth: bytes) -> bytes:
    """Independent RFC 8291 receiver, as a browser would do it."""
    salt, rs, idlen = body[:16], struct.unpack("!L", body[16:20])[0], body[20]
    as_public = body[21:21 + idlen]
    ciphertext = body[21 + idlen:]
    assert rs == 4096 and idlen == 65
    ua_public = public_key_bytes(ua_private.public_key())
    secret = ua_private.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), as_public))
    ikm = _h(_h(auth, secret), b"WebPush: info\x00" + ua_public + as_public + b"\x01")
    prk = _h(salt, ikm)
    cek = _h(prk, b"Content-Encoding: aes128gcm\x00\x01")[:16]
    nonce = _h(prk, b"Content-Encoding: nonce\x00\x01")[:12]
    padded = AESGCM(cek).decrypt(nonce, ciphertext, None)
    assert padded.endswith(b"\x02")
    return padded[:-1]


def test_payload_round_trips_through_an_independent_receiver():
    ua = ec.generate_private_key(ec.SECP256R1())
    auth = os.urandom(16)
    message = json.dumps({"title": "Heads-up", "body": "XAUUSD may signal BUY"}).encode()
    body = encrypt_payload(message, public_key_bytes(ua.public_key()), auth)
    assert _ua_decrypt(body, ua, auth) == message


def test_vapid_header_is_a_valid_es256_jwt_for_the_push_origin():
    pem = generate_vapid_private_key_pem()
    header = vapid_authorization("https://fcm.googleapis.com/fcm/send/abc", pem, "https://example.test", now=1_000)
    token = header.split("t=")[1].split(",")[0]
    k = header.split("k=")[1]
    head, claims, sig = token.split(".")
    raw = b64url_decode(sig)
    public = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), b64url_decode(k))
    public.verify(
        encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big")),
        f"{head}.{claims}".encode(),
        ec.ECDSA(hashes.SHA256()),
    )
    body = json.loads(b64url_decode(claims))
    assert body == {"aud": "https://fcm.googleapis.com", "exp": 1_000 + 12 * 3600, "sub": "https://example.test"}


def _keys():
    ua = ec.generate_private_key(ec.SECP256R1())
    return b64url_encode(public_key_bytes(ua.public_key())), b64url_encode(os.urandom(16))


def test_accepts_real_push_services():
    p256dh, auth = _keys()
    for endpoint in (
        "https://fcm.googleapis.com/fcm/send/abc",
        "https://updates.push.services.mozilla.com/wpush/v2/abc",
        "https://web.push.apple.com/abc",
    ):
        assert validate_subscription(endpoint, p256dh, auth).endpoint == endpoint


@pytest.mark.parametrize("endpoint", [
    "http://fcm.googleapis.com/x",  # not https
    "https://evil.example.com/x",  # not a push service
    "https://googleapis.com.evil.com/x",  # suffix trick
    "https://127.0.0.1/x",
])
def test_rejects_endpoints_that_are_not_browser_push_services(endpoint):
    p256dh, auth = _keys()
    with pytest.raises(ValueError):
        validate_subscription(endpoint, p256dh, auth)


def test_rejects_bad_keys():
    p256dh, auth = _keys()
    with pytest.raises(ValueError):
        validate_subscription("https://fcm.googleapis.com/x", "abc", auth)
    with pytest.raises(ValueError):
        validate_subscription("https://fcm.googleapis.com/x", p256dh, b64url_encode(b"short"))


def test_schedule_runs_heads_up_at_55_and_confirmation_after_the_close():
    service._done_slots.clear()
    at55 = datetime(2026, 9, 29, 5, 55, 10, tzinfo=timezone.utc)
    assert [j for j, _ in service.due_jobs(at55)] == ["heads_up"]
    at01 = datetime(2026, 9, 29, 6, 1, 5, tzinfo=timezone.utc)
    assert [j for j, _ in service.due_jobs(at01)] == ["confirm"]
    assert service.due_jobs(datetime(2026, 9, 29, 6, 30, tzinfo=timezone.utc)) == []
    # A job runs once per slot.
    for _, slot in service.due_jobs(at55):
        service._done_slots.add(slot)
    assert service.due_jobs(at55.replace(second=40)) == []
    service._done_slots.clear()


def _hourly(n, start, base=100.0):
    candles = []
    for i in range(n):
        o = base + (i % 5) * 0.2
        candles.append(Candle("XAU/USD", "h1", start + timedelta(hours=i), o, o + 0.5, o - 0.5, o + 0.1))
    return candles


class FakeProvider:
    def __init__(self, candles, price):
        self.candles, self.price = candles, price

    async def get_candles(self, instrument, timeframe, limit=200):
        return list(self.candles)

    async def get_current_price(self, instrument):
        return self.price


@pytest.mark.asyncio
async def test_heads_up_fires_when_the_forming_candle_breaks_out(monkeypatch):
    from app.research.hypothesis import HypothesisType
    from app.research.validated_strategy_config import ValidatedStrategyConfig

    now = datetime(2026, 9, 29, 5, 55, tzinfo=timezone.utc)
    start = now.replace(minute=0) - timedelta(hours=80)
    candles = _hourly(81, start)  # last one opens at 05:00 and is still forming
    config = ValidatedStrategyConfig(
        config_id="vsc_gold", candidate_id="cand_breakout_lookback_30", instrument="XAU/USD", timeframe="h1",
        strategy_family=HypothesisType.BREAKOUT, parameters={"lookback": 30},
        exit_config_summary={"atr_stop_multiple": 1.5}, cost_assumptions={},
        evidence_period_start="2012-01-01T00:00:00+00:00", evidence_period_end="2022-01-01T00:00:00+00:00",
        gate_status="PROMISING", verdict="PROMISING", statistical_level="WEAK",
        regime_evidence={r: 1 for r in ("TRENDING_UP", "TRENDING_DOWN", "RANGING", "HIGH_VOLATILITY", "LOW_VOLATILITY", "UNKNOWN")},
    )
    delivered = []

    async def fake_deliver(payload):
        delivered.append(payload)

    async def no_events(**_):
        return []

    monkeypatch.setattr(service, "_configs", lambda: [config])
    monkeypatch.setattr(service, "forward_test_config_ids", lambda: frozenset({"vsc_gold"}))
    monkeypatch.setattr(service, "get_market_data_provider", lambda *_a, **_k: FakeProvider(candles, 150.0))
    monkeypatch.setattr(service, "_deliver", fake_deliver)
    monkeypatch.setattr("app.news_engine.context.get_upcoming_macro_events", no_events)
    service._heads_up_sent.clear()

    sent = await service.heads_up_check(now)
    assert len(sent) == 1 and delivered == sent
    assert sent[0]["title"] == "Heads-up: XAUUSD may signal BUY"
    assert "forward test" in sent[0]["body"]

    # Same candle never alerts twice.
    assert await service.heads_up_check(now) == []

    # No breakout at the live price -> no heads-up.
    service._heads_up_sent.clear()
    delivered.clear()
    monkeypatch.setattr(service, "get_market_data_provider", lambda *_a, **_k: FakeProvider(candles, 100.4))
    assert await service.heads_up_check(now) == []
    service._heads_up_sent.clear()


def test_signal_message_carries_the_backend_levels():
    msg = service.signal_message("XAU/USD", {
        "decision": "BUY",
        "trade_plan": {"entry": 4129.8, "stop_loss": 4099.64, "take_profit": 4190.12},
        "forward_test": {"active": True},
    })
    assert msg["title"] == "Tembo signal: BUY XAUUSD (forward test)"
    assert "Entry 4,129.80" in msg["body"] and "SL 4,099.64" in msg["body"] and "TP 4,190.12" in msg["body"]
