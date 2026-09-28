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
        assert payload["duration"] == 3600
        assert payload["duration_unit"] == "s"
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
