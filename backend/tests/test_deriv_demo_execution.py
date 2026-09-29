import pytest

from app.integrations.deriv import DerivDemoClient, DerivAPIError
from app.api.routes.deriv import _sign_demo_authorization, _verify_demo_authorization


def client_without_init() -> DerivDemoClient:
    client = object.__new__(DerivDemoClient)
    return client


@pytest.mark.asyncio
async def test_demo_proposal_builds_multiplier_request():
    client = client_without_init()

    async def fake_resolve(instrument):
        return "1HZ100V"

    async def fake_ws(payload, expected):
        assert expected == "proposal"
        assert payload["proposal"] == 1
        assert payload["contract_type"] == "MULTUP"
        assert payload["underlying_symbol"] == "1HZ100V"
        assert payload["amount"] == 2.5
        assert payload["multiplier"] == 10
        assert "duration" not in payload  # multipliers have no fixed expiry
        assert payload["limit_order"] == {"stop_loss": 2.5, "take_profit": 5.0}
        return {"proposal": {"id": "p-1", "ask_price": 2.5, "spot": 100.0, "payout": 3.0}}

    client._resolve_underlying_symbol = fake_resolve
    client._ws_request = fake_ws
    result = await client.proposal(
        instrument="SYNTH:1HZ100V",
        direction="BUY",
        stake=2.5,
        multiplier=10,
        entry=100.0,
        stop_loss=90.0,
        take_profit=120.0,
    )
    assert result["proposal_id"] == "p-1"
    assert result["contract_type"] == "MULTUP"


@pytest.mark.asyncio
async def test_demo_proposal_retries_with_duration_only_if_deriv_requires_it():
    client = client_without_init()
    sent = []

    async def fake_resolve(instrument):
        return "frxUSDJPY"

    async def fake_ws(payload, expected):
        sent.append(payload)
        if "duration" not in payload:
            raise DerivAPIError("Deriv InputValidationFailed: duration is required")
        return {"proposal": {"id": "p-2", "ask_price": 1.0}}

    client._resolve_underlying_symbol = fake_resolve
    client._ws_request = fake_ws
    result = await client.proposal(instrument="USD/JPY", direction="SELL", stake=1, multiplier=50)
    assert result["proposal_id"] == "p-2" and result["contract_type"] == "MULTDOWN"
    assert len(sent) == 2 and sent[1]["duration"] == 3600


def test_price_levels_translate_to_deriv_money_thresholds():
    result = DerivDemoClient._price_levels_to_limit_order(
        direction="BUY",
        entry=100.0,
        stop_loss=90.0,
        take_profit=120.0,
        stake=2.5,
        multiplier=10,
    )
    assert result == {"stop_loss": 2.5, "take_profit": 5.0}


def test_price_levels_reverse_for_sell():
    result = DerivDemoClient._price_levels_to_limit_order(
        direction="SELL",
        entry=100.0,
        stop_loss=110.0,
        take_profit=80.0,
        stake=2.5,
        multiplier=10,
    )
    assert result == {"stop_loss": 2.5, "take_profit": 5.0}


@pytest.mark.asyncio
async def test_demo_proposal_rejects_unsafe_stake():
    client = client_without_init()
    with pytest.raises(DerivAPIError, match="no more than 10"):
        await client.proposal(instrument="SYNTH:1HZ100V", direction="BUY", stake=11, multiplier=10)


@pytest.mark.asyncio
async def test_demo_buy_returns_contract(monkeypatch):
    client = client_without_init()

    async def fake_ws(payload, expected):
        assert expected == "buy"
        assert payload["buy"] == "p-1"
        assert payload["price"] == 2.5
        return {"buy": {"contract_id": 12345, "transaction_id": 999, "buy_price": 2.5, "balance_after": 997.5}}

    client._ws_request = fake_ws
    result = await client.buy_demo(proposal_id="p-1", price=2.5)
    assert result["status"] == "EXECUTED_DEMO"
    assert result["contract_id"] == 12345
    assert result["balance_after"] == 997.5



def test_demo_execution_authorization_round_trip(monkeypatch):
    from app.core.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "deriv_api_token", "test-secret")
    token = _sign_demo_authorization(
        proposal_id="p-1",
        price=2.5,
        instrument="EUR/USD",
        direction="BUY",
    )
    _verify_demo_authorization(token, proposal_id="p-1", price=2.5)


def test_demo_execution_authorization_rejects_tampering(monkeypatch):
    from app.core.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "deriv_api_token", "test-secret")
    token = _sign_demo_authorization(
        proposal_id="p-1",
        price=2.5,
        instrument="EUR/USD",
        direction="BUY",
    )
    with pytest.raises(DerivAPIError):
        _verify_demo_authorization(token, proposal_id="p-1", price=2.6)


@pytest.mark.asyncio
async def test_demo_contract_update_sends_broker_protection():
    client = client_without_init()

    async def fake_ws(payload, expected):
        assert expected == "contract_update"
        assert payload == {
            "contract_update": 1,
            "contract_id": 12345,
            "limit_order": {"stop_loss": 2.5, "take_profit": 5.0},
            "req_id": 305,
        }
        return {"contract_update": {"stop_loss": {"order_amount": 2.5}, "take_profit": {"order_amount": 5.0}}}

    client._ws_request = fake_ws
    result = await client.update_contract_protection(
        contract_id=12345, stop_loss=2.5, take_profit=5.0
    )
    assert result["status"] == "UPDATED_DEMO"
    assert result["contract_id"] == 12345
    assert result["protection"]["stop_loss"]["order_amount"] == 2.5


@pytest.mark.asyncio
async def test_demo_contract_update_rejects_empty_protection():
    client = client_without_init()
    with pytest.raises(DerivAPIError, match="At least one protection"):
        await client.update_contract_protection(contract_id=12345)


@pytest.mark.asyncio
async def test_connection_test_opens_and_closes_a_one_dollar_demo_contract(monkeypatch):
    from app.api.routes import deriv as routes

    calls = []

    class FakeClient:
        async def account_status(self):
            calls.append("status")
            return {"account_id": "DOT1", "balance": 100.0, "currency": "USD", "open_positions": 0}

        async def proposal(self, **kw):
            calls.append(("proposal", kw["stake"], kw["multiplier"]))
            if kw["multiplier"] == 50:
                raise DerivAPIError("Multiplier is not in acceptable range")
            return {"proposal_id": "p1", "ask_price": 1.0, "currency": "USD", "multiplier": kw["multiplier"],
                    "protection": {"attached": True, "limit_order": {"stop_loss": 0.2}}}

        async def buy_demo(self, *, proposal_id, price):
            calls.append(("buy", proposal_id, price))
            return {"contract_id": 7, "buy_price": price}

        async def open_contract(self, contract_id):
            return {"contract": {"profit": -0.01, "status": "open"}}

        async def sell_demo(self, contract_id):
            calls.append(("sell", contract_id))
            return {"sold_for": 0.99}

    class FakeProvider:
        async def get_current_price(self, instrument):
            return 150.0

    async def no_sleep(_):
        return None

    monkeypatch.setattr(routes, "DerivDemoClient", FakeClient)
    monkeypatch.setattr("app.data_engine.market_data.get_market_data_provider", lambda *a, **k: FakeProvider())
    monkeypatch.setattr("asyncio.sleep", no_sleep)
    routes._last_selftest["at"] = 0.0

    result = await routes.deriv_demo_selftest({"instrument": "USD/JPY"})
    assert result["status"] == "PASSED", result
    assert ("proposal", 1.0, 100) in calls
    assert ("buy", "p1", 1.0) in calls and ("sell", 7) in calls  # always closed again

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:  # rate-limited
        await routes.deriv_demo_selftest({"instrument": "USD/JPY"})
    assert exc.value.status_code == 429
    routes._last_selftest["at"] = 0.0


@pytest.mark.asyncio
async def test_proposal_switches_to_the_smallest_multiplier_deriv_accepts():
    client = client_without_init()
    sent = []

    async def fake_resolve(instrument):
        return "frxUSDJPY"

    async def fake_ws(payload, expected):
        sent.append(payload)
        if payload["multiplier"] not in (100, 200, 300, 500, 800):
            raise DerivAPIError("Deriv ContractBuyValidationError: Multiplier is not in acceptable range. Accepts 100,200,300,500,800.")
        return {"proposal": {"id": "p-3", "ask_price": 1.0}}

    client._resolve_underlying_symbol = fake_resolve
    client._ws_request = fake_ws
    result = await client.proposal(
        instrument="USD/JPY", direction="BUY", stake=1, multiplier=50,
        entry=150.0, stop_loss=149.25, take_profit=150.75,
    )
    assert result["multiplier"] == 100
    assert sent[-1]["multiplier"] == 100
    # 0.5% move x100 x $1 stake = $0.50 thresholds, re-priced for the new multiplier
    assert sent[-1]["limit_order"] == {"stop_loss": 0.5, "take_profit": 0.5}


def test_accepted_multipliers_parsing():
    from app.integrations.deriv import accepted_multipliers

    assert accepted_multipliers("Multiplier is not in acceptable range. Accepts 100,200,300,500,800.") == [100, 200, 300, 500, 800]
    assert accepted_multipliers("some other error") == []
