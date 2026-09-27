import json
from unittest.mock import patch

import pytest

from app.data_engine.market_data import get_market_data_provider
from app.data_engine.providers.deriv_synthetics import DerivSyntheticProvider, SYNTHETIC_PREFIX


class FakeWebSocket:
    def __init__(self, responses):
        self.responses = [json.dumps(item) for item in responses]
        self.sent = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def send(self, payload):
        self.sent.append(json.loads(payload))

    async def recv(self):
        return self.responses.pop(0)


class FakeConnect:
    def __init__(self, response_batches):
        self.response_batches = list(response_batches)

    def __call__(self, *args, **kwargs):
        return FakeWebSocket(self.response_batches.pop(0))


def test_synthetic_prefix_is_explicit():
    assert DerivSyntheticProvider.is_synthetic_instrument("SYNTH:1HZ100V")
    assert not DerivSyntheticProvider.is_synthetic_instrument("EUR/USD")
    assert DerivSyntheticProvider.provider_symbol("SYNTH:1HZ100V") == "1HZ100V"


def test_factory_routes_synthetic_to_deriv(monkeypatch):
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "twelvedata")
    from app.core.config import get_settings
    get_settings.cache_clear()
    provider = get_market_data_provider("twelvedata", "SYNTH:1HZ100V")
    assert isinstance(provider, DerivSyntheticProvider)
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_active_symbols_filters_to_unsuspended_synthetics(monkeypatch):
    from app.core.config import get_settings
    get_settings.cache_clear()
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "twelvedata")
    provider = DerivSyntheticProvider()
    fake = FakeConnect([[
        {
            "msg_type": "active_symbols",
            "active_symbols": [
                {
                    "underlying_symbol": "1HZ100V",
                    "underlying_symbol_name": "Volatility 100 (1s) Index",
                    "underlying_symbol_type": "synthetic_index",
                    "market": "synthetic_index",
                    "submarket": "random_index",
                    "subgroup": "volatility_indices",
                    "pip_size": 0.01,
                    "exchange_is_open": 1,
                    "is_trading_suspended": 0,
                },
                {
                    "underlying_symbol": "R_100",
                    "underlying_symbol_name": "Volatility 100 Index",
                    "underlying_symbol_type": "synthetic_index",
                    "market": "synthetic_index",
                    "is_trading_suspended": 1,
                },
                {
                    "underlying_symbol": "frxEURUSD",
                    "underlying_symbol_name": "EUR/USD",
                    "underlying_symbol_type": "forex",
                    "market": "forex",
                    "is_trading_suspended": 0,
                },
            ],
        }]])
    with patch("app.data_engine.providers.deriv_synthetics.websockets.connect", fake):
        symbols = await provider.get_active_synthetics()
    assert [item["symbol"] for item in symbols] == [f"{SYNTHETIC_PREFIX}1HZ100V"]
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_candles_are_normalized_to_tembo_candle_shape(monkeypatch):
    from app.core.config import get_settings
    get_settings.cache_clear()
    provider = DerivSyntheticProvider()
    fake = FakeConnect([[
        {
            "msg_type": "active_symbols",
            "active_symbols": [
                {
                    "underlying_symbol": "1HZ100V",
                    "underlying_symbol_name": "Volatility 100 (1s) Index",
                    "underlying_symbol_type": "synthetic_index",
                    "market": "synthetic_index",
                    "pip_size": 0.01,
                    "exchange_is_open": 1,
                    "is_trading_suspended": 0,
                }
            ],
        }], [{
            "msg_type": "candles",
            "candles": [
                {"epoch": 1000, "open": "10", "high": "12", "low": "9", "close": "11"},
                {"epoch": 1360, "open": "11", "high": "13", "low": "10", "close": "12"},
            ],
        }]])
    with patch("app.data_engine.providers.deriv_synthetics.websockets.connect", fake):
        candles = await provider.get_candles("SYNTH:1HZ100V", "m5", limit=2)
    assert len(candles) == 2
    assert candles[0].open == 10.0
    assert candles[1].close == 12.0
    assert candles[0].symbol == "SYNTH:1HZ100V"
    get_settings.cache_clear()
