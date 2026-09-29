"""
Minimal, dependency-light Web Push sender (RFC 8291 aes128gcm + RFC 8292 VAPID).

Implemented directly on `cryptography` so the backend does not need an extra
native-build dependency. Payloads are small JSON messages for the Tembo
dashboard's service worker; nothing here can place or change a trade.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import struct
import time
from dataclasses import dataclass
from urllib.parse import urlparse

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

RECORD_SIZE = 4096

# Only well-known browser push services may be used as endpoints. This keeps
# the backend from being used to send requests to arbitrary URLs.
ALLOWED_PUSH_HOST_SUFFIXES = (
    ".googleapis.com",  # Chrome / Android (FCM)
    ".mozilla.com",  # Firefox
    ".push.apple.com",  # Safari / iOS
    ".notify.windows.com",  # Edge (WNS)
)


def b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def b64url_decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _hmac_sha256(key: bytes, data: bytes) -> bytes:
    return hmac.new(key, data, hashlib.sha256).digest()


def public_key_bytes(key: ec.EllipticCurvePublicKey) -> bytes:
    return key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)


def generate_vapid_private_key_pem() -> str:
    key = ec.generate_private_key(ec.SECP256R1())
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()


def load_private_key(pem: str) -> ec.EllipticCurvePrivateKey:
    key = serialization.load_pem_private_key(pem.encode(), password=None)
    if not isinstance(key, ec.EllipticCurvePrivateKey) or key.curve.name != "secp256r1":
        raise ValueError("VAPID key must be a P-256 EC private key.")
    return key


def application_server_key(private_pem: str) -> str:
    """The base64url public key the browser needs for PushManager.subscribe()."""
    return b64url_encode(public_key_bytes(load_private_key(private_pem).public_key()))


@dataclass(frozen=True)
class Subscription:
    endpoint: str
    p256dh: str
    auth: str


def validate_subscription(endpoint: str, p256dh: str, auth: str) -> Subscription:
    """Reject anything that is not a real browser push subscription."""
    if not isinstance(endpoint, str) or len(endpoint) > 2048:
        raise ValueError("Invalid push endpoint.")
    parsed = urlparse(endpoint)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not host.endswith(ALLOWED_PUSH_HOST_SUFFIXES):
        raise ValueError("Push endpoint must be an https URL on a known browser push service.")
    try:
        key = b64url_decode(p256dh)
        secret = b64url_decode(auth)
    except (ValueError, TypeError) as exc:
        raise ValueError("Push keys are not valid base64url.") from exc
    if len(key) != 65 or key[0] != 0x04:
        raise ValueError("p256dh must be an uncompressed P-256 public key.")
    if len(secret) != 16:
        raise ValueError("auth secret must be 16 bytes.")
    # Make sure the point is actually on the curve.
    ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), key)
    return Subscription(endpoint, p256dh, auth)


def encrypt_payload(
    plaintext: bytes,
    ua_public: bytes,
    auth_secret: bytes,
    *,
    _as_private: ec.EllipticCurvePrivateKey | None = None,
    _salt: bytes | None = None,
) -> bytes:
    """RFC 8291 message encryption with the aes128gcm content coding (single record)."""
    if len(plaintext) > RECORD_SIZE - 17:
        raise ValueError("Push payload too large.")
    as_private = _as_private or ec.generate_private_key(ec.SECP256R1())
    as_public = public_key_bytes(as_private.public_key())
    ua_key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_public)
    ecdh_secret = as_private.exchange(ec.ECDH(), ua_key)

    prk_key = _hmac_sha256(auth_secret, ecdh_secret)
    ikm = _hmac_sha256(prk_key, b"WebPush: info\x00" + ua_public + as_public + b"\x01")

    salt = _salt or os.urandom(16)
    prk = _hmac_sha256(salt, ikm)
    cek = _hmac_sha256(prk, b"Content-Encoding: aes128gcm\x00\x01")[:16]
    nonce = _hmac_sha256(prk, b"Content-Encoding: nonce\x00\x01")[:12]

    ciphertext = AESGCM(cek).encrypt(nonce, plaintext + b"\x02", None)
    header = salt + struct.pack("!L", RECORD_SIZE) + bytes([len(as_public)]) + as_public
    return header + ciphertext


def vapid_authorization(endpoint: str, private_pem: str, subject: str, *, now: int | None = None) -> str:
    """RFC 8292 `Authorization: vapid t=..., k=...` header value."""
    parsed = urlparse(endpoint)
    audience = f"{parsed.scheme}://{parsed.netloc}"
    issued = int(now if now is not None else time.time())
    header = b64url_encode(json.dumps({"typ": "JWT", "alg": "ES256"}, separators=(",", ":")).encode())
    claims = b64url_encode(
        json.dumps({"aud": audience, "exp": issued + 12 * 3600, "sub": subject}, separators=(",", ":")).encode()
    )
    signing_input = f"{header}.{claims}".encode()
    key = load_private_key(private_pem)
    der = key.sign(signing_input, ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der)
    signature = b64url_encode(r.to_bytes(32, "big") + s.to_bytes(32, "big"))
    token = f"{header}.{claims}.{signature}"
    return f"vapid t={token}, k={application_server_key(private_pem)}"


def build_push_request(sub: Subscription, payload: dict, private_pem: str, subject: str, ttl: int = 3600) -> tuple[dict, bytes]:
    body = encrypt_payload(
        json.dumps(payload, separators=(",", ":")).encode(),
        b64url_decode(sub.p256dh),
        b64url_decode(sub.auth),
    )
    headers = {
        "Authorization": vapid_authorization(sub.endpoint, private_pem, subject),
        "Content-Encoding": "aes128gcm",
        "Content-Type": "application/octet-stream",
        "TTL": str(ttl),
        "Urgency": "high",
    }
    return headers, body
