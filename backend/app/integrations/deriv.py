"""Server-side Deriv demo-account client.

Credentials never leave the backend. This client is explicitly demo-only.
It supports account telemetry and controlled demo contract operations; it
cannot connect to a real-money Deriv endpoint.
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

    async def _ws_exchange(self, payload: dict[str, Any], expected: str) -> dict[str, Any]:
        return await self._ws_request(payload, expected)

    async def markets(self) -> dict[str, Any]:
        # Reuse the public catalogue through the same backend so the browser
        # never needs to know Deriv's WebSocket URL or credentials.
        from app.data_engine.providers.deriv import DerivMarketDataProvider
        provider = DerivMarketDataProvider()
        symbols = await provider.get_active_markets()
        return {"status": "AVAILABLE", "symbols": symbols}

    async def proposal(
        self,
        underlying_symbol: str,
        contract_type: str,
        amount: float,
        duration: int = 60,
        duration_unit: str = "s",
        multiplier: float | None = None,
    ) -> dict[str, Any]:
        if amount <= 0:
            raise DerivAPIError("Demo stake must be greater than zero.")
        contract_type = contract_type.upper()
        allowed = {"CALL", "PUT", "MULTUP", "MULTDOWN"}
        if contract_type not in allowed:
            raise DerivAPIError("Unsupported demo contract type.")
        payload: dict[str, Any] = {
            "proposal": 1,
            "amount": amount,
            "basis": "stake",
            "contract_type": contract_type,
            "currency": "USD",
            "duration": duration,
            "duration_unit": duration_unit,
            "underlying_symbol": underlying_symbol,
            "req_id": 201,
        }
        if multiplier is not None:
            if multiplier <= 0:
                raise DerivAPIError("Multiplier must be greater than zero.")
            payload["multiplier"] = multiplier
        return await self._ws_exchange(payload, "proposal")

    async def buy_demo_contract(self, proposal_id: str, price: float) -> dict[str, Any]:
        if not proposal_id:
            raise DerivAPIError("A Deriv proposal ID is required.")
        if price <= 0:
            raise DerivAPIError("Proposal price must be greater than zero.")
        return await self._ws_exchange(
            {"buy": proposal_id, "price": price, "req_id": 202},
            "buy",
        )

    async def open_contract(self, contract_id: str) -> dict[str, Any]:
        if not contract_id:
            raise DerivAPIError("A Deriv contract ID is required.")
        return await self._ws_exchange(
            {"proposal_open_contract": 1, "contract_id": contract_id, "req_id": 203},
            "proposal_open_contract",
        )

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
