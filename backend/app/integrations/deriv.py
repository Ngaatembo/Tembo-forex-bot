"""Server-side Deriv demo-account client.

Credentials never leave the backend. This client is explicitly demo-only.
It supports account telemetry and controlled demo contract operations; it
cannot connect to a real-money Deriv endpoint.
"""

from __future__ import annotations

import asyncio
import json
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import httpx
import websockets

from app.core.config import get_settings


MAX_DEMO_MULTIPLIER = 1000


def accepted_multipliers(message: str) -> list[int]:
    """Parse Deriv's 'Multiplier is not in acceptable range. Accepts 100,200,...' error."""
    import re

    match = re.search(r"accepts\s+([\d,\s]+)", message, flags=re.IGNORECASE)
    if not match:
        return []
    return sorted({int(v) for v in re.findall(r"\d+", match.group(1))})


class DerivConfigurationError(RuntimeError):
    pass


class DerivAPIError(RuntimeError):
    pass


def _clean_setting(value: str | None) -> str | None:
    """Drop whitespace and wrapping quotes that often sneak in when pasting env vars."""
    if value is None:
        return None
    cleaned = value.strip().strip('"').strip("'").strip()
    return cleaned or None


class DerivDemoClient:
    _session_ws: Any = None

    def __init__(self) -> None:
        settings = get_settings()
        self.base_url = "https://api.derivws.com"
        self.token = _clean_setting(settings.deriv_api_token)
        self.app_id = _clean_setting(settings.deriv_app_id)
        self.account_id = _clean_setting(settings.deriv_account_id)
        raw_mode = _clean_setting(settings.deriv_trading_mode) or "demo"
        self.mode = raw_mode.lower()

        if self.mode != "demo":
            raise DerivConfigurationError(
                "Tembo's first direct Deriv integration is demo-only. "
                f"DERIV_TRADING_MODE is currently {raw_mode!r}; set its value to exactly: demo"
            )
        if not self.token or not self.account_id:
            raise DerivConfigurationError(
                "DERIV_API_TOKEN and DERIV_ACCOUNT_ID are required for "
                "authenticated Deriv demo telemetry."
            )
        # When set, every request goes over this one authenticated connection.
        # Deriv only recognises a proposal id on the connection that created it,
        # so a quote and the buy that uses it must share a session.
        self._session_ws: Any = None

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

    @staticmethod
    async def _exchange_on(ws: Any, payload: dict[str, Any], expected: str) -> dict[str, Any]:
        await ws.send(json.dumps(payload))
        req_id = payload.get("req_id")
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=max(0.1, deadline - time.monotonic()))
            except asyncio.TimeoutError:
                break
            message = json.loads(raw)
            # On a shared session, skip anything that answers an earlier request.
            if req_id is not None and message.get("req_id") not in (None, req_id):
                continue
            if message.get("error"):
                error = message["error"]
                raise DerivAPIError(
                    f"Deriv {error.get('code')}: {error.get('message')}"
                )
            if message.get("msg_type") == expected:
                return message
        raise DerivAPIError(f"Timed out waiting for Deriv {expected} response.")

    @asynccontextmanager
    async def session(self) -> AsyncIterator["DerivDemoClient"]:
        """Run several requests on ONE authenticated Deriv connection (one OTP)."""
        if self._session_ws is not None:
            yield self
            return
        ws_url = await self._get_ws_url()
        try:
            connection = websockets.connect(ws_url, open_timeout=15, close_timeout=5)
            ws = await connection.__aenter__()
        except Exception as exc:
            raise DerivAPIError(f"Deriv WebSocket connection failed: {exc}") from exc
        self._session_ws = ws
        try:
            yield self
        finally:
            self._session_ws = None
            try:
                await connection.__aexit__(None, None, None)
            except Exception:
                pass

    async def _ws_request(self, payload: dict[str, Any], expected: str) -> dict[str, Any]:
        try:
            if self._session_ws is not None:
                return await self._exchange_on(self._session_ws, payload, expected)
            ws_url = await self._get_ws_url()
            async with websockets.connect(
                ws_url, open_timeout=15, close_timeout=5
            ) as ws:
                return await self._exchange_on(ws, payload, expected)
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

    async def _resolve_underlying_symbol(self, instrument: str) -> str:
        """Resolve Tembo instrument names to the current Deriv symbol catalogue."""
        normalized = instrument.strip().upper()
        from app.data_engine.providers.deriv import DerivMarketDataProvider
        from app.data_engine.providers.deriv_synthetics import DerivSyntheticProvider

        if normalized.startswith("SYNTH:"):
            provider_symbol = DerivSyntheticProvider.provider_symbol(normalized)
            for item in await DerivSyntheticProvider().get_active_synthetics():
                if str(item.get("underlying_symbol", "")).upper() == provider_symbol:
                    return provider_symbol
            raise DerivAPIError(f"Synthetic market {instrument!r} is not currently active.")

        aliases = {
            "EUR/USD": {"EURUSD", "FRXEURUSD"},
            "EURUSD": {"EURUSD", "FRXEURUSD"},
            "GBP/USD": {"GBPUSD", "FRXGBPUSD"},
            "GBPUSD": {"GBPUSD", "FRXGBPUSD"},
            "USD/JPY": {"USDJPY", "FRXUSDJPY"},
            "USDJPY": {"USDJPY", "FRXUSDJPY"},
            "XAU/USD": {"XAUUSD", "GOLDUSD", "FRXXAUUSD"},
            "XAUUSD": {"XAUUSD", "GOLDUSD", "FRXXAUUSD"},
        }.get(normalized, {normalized.replace("/", "")})

        for item in await DerivMarketDataProvider().get_active_markets():
            values = {
                str(item.get("underlying_symbol", "")).upper(),
                str(item.get("symbol", "")).upper(),
                str(item.get("display_name", "")).upper().replace("/", "").replace(" ", ""),
            }
            if values & aliases or {v[3:] for v in values if v.startswith("FRX")} & aliases:
                return str(item["underlying_symbol"])
        raise DerivAPIError(f"Could not resolve {instrument!r} to an active Deriv symbol.")

    @staticmethod
    def _price_levels_to_limit_order(
        *,
        direction: str,
        entry: float | None,
        stop_loss: float | None,
        take_profit: float | None,
        stake: float,
        multiplier: float,
    ) -> dict[str, float]:
        """Translate Tembo price levels into Deriv multiplier P/L thresholds.

        Deriv multiplier limit orders are monetary profit/loss thresholds, not
        underlying-market price levels. Tembo converts its price plan using
        the documented multiplier relationship: percentage move x multiplier x stake.

        A level that cannot be converted safely is omitted rather than guessed.
        """
        if entry is None or not entry > 0:
            return {}
        side = direction.upper()
        if side not in {"BUY", "SELL"}:
            return {}

        def gross_pnl(level: float | None) -> float | None:
            if level is None or not level > 0:
                return None
            move = ((level - entry) / entry) if side == "BUY" else ((entry - level) / entry)
            return move * multiplier * stake

        stop_value = gross_pnl(stop_loss)
        take_value = gross_pnl(take_profit)
        result: dict[str, float] = {}
        if stop_value is not None and stop_value < 0:
            result["stop_loss"] = round(abs(stop_value), 2)
        if take_value is not None and take_value > 0:
            result["take_profit"] = round(take_value, 2)
        return result

    async def proposal(
        self,
        *,
        instrument: str,
        direction: str,
        stake: float,
        multiplier: float,
        entry: float | None = None,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> dict[str, Any]:
        if not 0 < stake <= 10:
            raise DerivAPIError("Demo stake must be greater than 0 and no more than 10 USD.")
        # A multiplier contract can never lose more than its stake, so the
        # $10 stake cap is the real money limit. Deriv itself decides which
        # multipliers a market accepts (e.g. USD/JPY: 100-800).
        if not 0 < multiplier <= MAX_DEMO_MULTIPLIER:
            raise DerivAPIError(f"Demo multiplier must be greater than 0 and no more than {MAX_DEMO_MULTIPLIER}.")
        side = direction.upper()
        if side not in {"BUY", "SELL"}:
            raise DerivAPIError("Direction must be BUY or SELL.")
        underlying = await self._resolve_underlying_symbol(instrument)
        contract_type = "MULTUP" if side == "BUY" else "MULTDOWN"
        limit_order = self._price_levels_to_limit_order(
            direction=side,
            entry=entry,
            stop_loss=stop_loss,
            take_profit=take_profit,
            stake=stake,
            multiplier=multiplier,
        )
        request: dict[str, Any] = {
            "proposal": 1,
            "amount": round(stake, 2),
            "basis": "stake",
            "contract_type": contract_type,
            "currency": "USD",
            "multiplier": multiplier,
            "underlying_symbol": underlying,
            "req_id": 301,
        }
        if limit_order:
            request["limit_order"] = limit_order
        # Multiplier contracts normally have no fixed expiry. If Deriv insists
        # on a duration, retry once with the previously used 1-hour duration.
        try:
            response = await self._ws_request(request, "proposal")
        except DerivAPIError as exc:
            accepted = accepted_multipliers(str(exc))
            if accepted and multiplier not in accepted:
                # Use the smallest multiplier Deriv accepts for this market and
                # re-price the stop/target thresholds for it.
                multiplier = min(accepted)
                if multiplier > MAX_DEMO_MULTIPLIER:
                    raise DerivAPIError(f"Deriv only accepts multipliers {accepted} here, above Tembo's demo cap of {MAX_DEMO_MULTIPLIER}.") from exc
                limit_order = self._price_levels_to_limit_order(
                    direction=side, entry=entry, stop_loss=stop_loss, take_profit=take_profit,
                    stake=stake, multiplier=multiplier,
                )
                request = {**request, "multiplier": multiplier}
                request.pop("limit_order", None)
                if limit_order:
                    request["limit_order"] = limit_order
                response = await self._ws_request(request, "proposal")
            elif "duration" in str(exc).lower():
                response = await self._ws_request({**request, "duration": 3600, "duration_unit": "s"}, "proposal")
            else:
                raise
        proposal = response.get("proposal") or {}
        proposal_id = proposal.get("id")
        ask_price = proposal.get("ask_price")
        if not proposal_id or ask_price is None:
            raise DerivAPIError("Deriv proposal response did not contain an id and ask price.")
        return {
            "status": "AVAILABLE",
            "instrument": instrument,
            "underlying_symbol": underlying,
            "direction": side,
            "contract_type": contract_type,
            "stake": stake,
            "multiplier": multiplier,
            "proposal_id": proposal_id,
            "ask_price": float(ask_price),
            "spot": float(proposal["spot"]) if proposal.get("spot") is not None else None,
            "payout": float(proposal["payout"]) if proposal.get("payout") is not None else None,
            "currency": proposal.get("currency") or "USD",
            "protection": {
                "attached": bool(limit_order),
                "limit_order": limit_order,
                "source": "TEMBO_PRICE_PLAN",
            },
        }

    async def buy_demo(
        self,
        *,
        proposal_id: str,
        price: float,
    ) -> dict[str, Any]:
        if not proposal_id or not 0 < price <= 10:
            raise DerivAPIError("Invalid demo proposal or price.")
        response = await self._ws_request(
            {"buy": str(proposal_id), "price": round(price, 2), "req_id": 302},
            "buy",
        )
        buy = response.get("buy") or {}
        contract_id = buy.get("contract_id")
        if contract_id is None:
            raise DerivAPIError("Deriv buy response did not contain a contract id.")
        return {
            "status": "EXECUTED_DEMO",
            "contract_id": int(contract_id),
            "transaction_id": buy.get("transaction_id"),
            "buy_price": float(buy["buy_price"]) if buy.get("buy_price") is not None else price,
            "balance_after": float(buy["balance_after"]) if buy.get("balance_after") is not None else None,
        }

    async def quote_and_buy_demo(
        self,
        *,
        instrument: str,
        direction: str,
        stake: float,
        multiplier: float,
        max_price: float | None = None,
        entry: float | None = None,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> dict[str, Any]:
        """Price the contract and buy it on the same Deriv connection.

        Deriv rejects a proposal id used on another connection with
        'InvalidContractProposal: Unknown contract proposal', so the quote
        and the buy can never be split across two sessions.
        """
        async with self.session():
            quote = await self.proposal(
                instrument=instrument,
                direction=direction,
                stake=stake,
                multiplier=multiplier,
                entry=entry,
                stop_loss=stop_loss,
                take_profit=take_profit,
            )
            price = float(quote["ask_price"])
            if max_price is not None and price > max_price + 1e-9:
                raise DerivAPIError(
                    f"Deriv now asks {price} USD, above the {max_price} USD you confirmed. Nothing was bought."
                )
            bought = await self.buy_demo(proposal_id=str(quote["proposal_id"]), price=price)
        return {
            **bought,
            "instrument": quote["instrument"],
            "direction": quote["direction"],
            "multiplier": quote["multiplier"],
            "stake": quote["stake"],
            "protection": quote["protection"],
        }

    async def open_contract(self, contract_id: int) -> dict[str, Any]:
        response = await self._ws_request(
            {"proposal_open_contract": 1, "contract_id": int(contract_id), "subscribe": 1, "req_id": 303},
            "proposal_open_contract",
        )
        return {"status": "AVAILABLE", "contract": response.get("proposal_open_contract") or {}}

    async def account_balance(self) -> dict[str, Any]:
        """Return the broker-confirmed demo balance for the configured account."""
        response = await self._ws_request({"balance": 1, "req_id": 103}, "balance")
        data = response.get("balance") or {}
        return {
            "balance": float(data["balance"]) if data.get("balance") is not None else None,
            "currency": data.get("currency") or "USD",
        }

    async def contract_update_history(self, contract_id: int) -> dict[str, Any]:
        """Return broker-confirmed SL/TP update history for a demo contract."""
        if contract_id <= 0:
            raise DerivAPIError("Invalid demo contract id.")
        response = await self._ws_request(
            {
                "contract_update_history": 1,
                "contract_id": int(contract_id),
                "limit": 20,
                "req_id": 306,
            },
            "contract_update_history",
        )
        return {
            "status": "AVAILABLE",
            "contract_id": int(contract_id),
            "history": response.get("contract_update_history") or [],
        }

    async def update_contract_protection(
        self,
        *,
        contract_id: int,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> dict[str, Any]:
        """Update broker-side monetary protection on an open demo contract."""
        if contract_id <= 0:
            raise DerivAPIError("Invalid demo contract id.")
        limit_order: dict[str, float] = {}
        if stop_loss is not None:
            if not 0 < float(stop_loss) <= 10000:
                raise DerivAPIError("Stop-loss protection must be between 0 and 10000 USD.")
            limit_order["stop_loss"] = round(float(stop_loss), 2)
        if take_profit is not None:
            if not 0 < float(take_profit) <= 10000:
                raise DerivAPIError("Take-profit protection must be between 0 and 10000 USD.")
            limit_order["take_profit"] = round(float(take_profit), 2)
        if not limit_order:
            raise DerivAPIError("At least one protection threshold is required.")

        response = await self._ws_request(
            {
                "contract_update": 1,
                "contract_id": int(contract_id),
                "limit_order": limit_order,
                "req_id": 305,
            },
            "contract_update",
        )
        updated = response.get("contract_update") or {}
        return {
            "status": "UPDATED_DEMO",
            "contract_id": int(contract_id),
            "protection": updated,
        }

    async def sell_demo(self, contract_id: int) -> dict[str, Any]:
        response = await self._ws_request(
            {"sell": int(contract_id), "price": 0, "req_id": 304},
            "sell",
        )
        sell = response.get("sell") or {}
        return {
            "status": "CLOSED_DEMO",
            "contract_id": int(contract_id),
            "transaction_id": sell.get("transaction_id"),
            "sold_for": float(sell["sold_for"]) if sell.get("sold_for") is not None else None,
        }

    async def account_status(self) -> dict[str, Any]:
        """Verify the configured account by obtaining its authenticated WS URL.

        The status check deliberately avoids the account-list REST endpoint.
        A configured account ID is sufficient for the OTP flow, and the OTP
        response tells us whether Deriv is issuing a demo or real WebSocket URL.
        Tembo fails closed unless Deriv explicitly returns the demo endpoint.
        """
        if not self.app_id:
            raise DerivConfigurationError(
                "DERIV_APP_ID is required for the configured Deriv PAT. "
                "Create/use a current Deriv API application ID; legacy app IDs are not accepted by the new API."
            )

        ws_url = await self._get_ws_url()
        if "/trading/v1/options/ws/demo" not in ws_url:
            raise DerivConfigurationError(
                "Tembo refused the configured Deriv account because Deriv did not issue a demo WebSocket URL."
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
            "configured": True,
            "mode": "demo",
            "account_id": self.account_id,
            "account_type": "demo",
            "status": "authenticated",
            "currency": balance_data.get("currency"),
            "balance": balance_data.get("balance"),
            "open_positions": len(contracts) if isinstance(contracts, list) else 0,
            "positions": contracts if isinstance(contracts, list) else [],
            "message": "Deriv demo account authenticated successfully.",
        }
