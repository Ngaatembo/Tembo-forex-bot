"""Small, server-side Deriv demo-account client.

Credentials never leave the backend. This module deliberately exposes only
read-only account telemetry for the first integration step. Trade methods can
be added behind the existing risk/execution gates after demo connectivity is
verified.
"""

from __future__ import annotations

import time
from typing import Any

import httpx
import websockets

from app.core.config import get_settings


class DerivConfigurationError(RuntimeError):
    pass


class DerivAPIError(RuntimeError):
    pass


class DerivDemoClient:
    def __init__(self) -> None:
        settings = get_settings()
        self.base_url = "https://api.derivws.com"
        self.token = settings.deriv_api_token
        self.app_id = settings.deriv_app_id
        self.account_id = settings.deriv_account_id
        self.mode = settings.deriv_trading_mode.lower()

        if self.mode != "demo":
            raise DerivConfigurationError(
                "Tembo's first direct Deriv integration is demo-only. "
                "Set DERIV_TRADING_MODE=demo."
            )
        if not self.token or not self.account_id:
            raise DerivConfigurationError(
                "DERIV_API_TOKEN and DERIV_ACCOUNT_ID are required for "
                "authenticated Deriv demo telemetry."
            )

    def _headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        if self.app_id:
            headers["Deriv-App-ID"] = self.app_id
        return headers

    async def _get(self, path: str) -> dict[str, Any]:
        async with httpx.AsyncClient(
            base_url=self.base_url, headers=self._headers(), timeout=20.0
        ) as client:
            response = await client.get(path)
            if response.status_code >= 400:
                raise DerivAPIError(
                    f"Deriv REST {response.status_code}: {response.text[:300]}"
                )
            return response.json()

    async def _get_ws_url(self) -> str:
        async with httpx.AsyncClient(
            base_url=self.base_url, headers=self._headers(), timeout=20.0
        ) as client:
            response = await client.post(
                f"/trading/v1/options/accounts/{self.account_id}/otp"
            )
            if response.status_code >= 400:
                raise DerivAPIError(
                    f"Deriv OTP {response.status_code}: {response.text[:300]}"
                )
            payload = response.json()
        url = payload.get("data", {}).get("url")
        if not url:
            raise DerivAPIError("Deriv OTP response did not contain a WebSocket URL.")
        return url

    async def _ws_request(self, payload: dict[str, Any], expected: str) -> dict[str, Any]:
        ws_url = await self._get_ws_url()
        try:
            async with websockets.connect(
                ws_url, open_timeout=15, close_timeout=5
            ) as ws:
                await ws.send(__import__("json").dumps(payload))
                deadline = time.monotonic() + 20
                while time.monotonic() < deadline:
                    raw = await ws.recv()
                    message = __import__("json").loads(raw)
                    if message.get("error"):
                        error = message["error"]
                        raise DerivAPIError(
                            f"Deriv {error.get('code')}: {error.get('message')}"
                        )
                    if message.get("msg_type") == expected:
                        return message
                raise DerivAPIError(f"Timed out waiting for Deriv {expected} response.")
        except DerivAPIError:
            raise
        except Exception as exc:
            raise DerivAPIError(f"Deriv WebSocket connection failed: {exc}") from exc

    async def account_status(self) -> dict[str, Any]:
        payload = await self._get("/trading/v1/options/accounts")
        raw_accounts = payload.get("data", [])
        if isinstance(raw_accounts, dict):
            raw_accounts = [raw_accounts]
        account = next(
            (item for item in raw_accounts if item.get("account_id") == self.account_id),
            None,
        )
        if account is None:
            raise DerivAPIError(
                f"Configured Deriv account {self.account_id!r} was not returned by the API."
            )
        if str(account.get("account_type", "")).lower() != "demo":
            raise DerivConfigurationError(
                "Tembo refused the configured Deriv account because it is not a demo account."
            )

        balance = await self._ws_request(
            {"balance": 1, "req_id": 101},
            "balance",
        )
        portfolio = await self._ws_request(
            {"portfolio": 1, "req_id": 102},
            "portfolio",
        )

        balance_data = balance.get("balance", {})
        contracts = portfolio.get("portfolio", {}).get("contracts", [])
        return {
            "connected": True,
            "mode": "demo",
            "account_id": self.account_id,
            "account_type": account.get("account_type"),
            "status": account.get("status"),
            "currency": balance_data.get("currency") or account.get("currency"),
            "balance": balance_data.get("balance"),
            "open_positions": len(contracts) if isinstance(contracts, list) else 0,
            "positions": contracts if isinstance(contracts, list) else [],
            "message": "Deriv demo account authenticated successfully.",
        }
