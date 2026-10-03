import json
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from app.data_engine.market_data import get_market_data_provider
from app.data_engine.providers.deriv import DerivMarketDataProvider


class FakeWebSocket:
    def __init__(self, responses):
        self.responses = [json.dumps(item) for item in responses]
        self.sent = []

    @property
    def closed(self):
        return False

    def __await__(self):
        async def _ready():
            return self
        return _ready().__await__()

    async def close(self):
        return None

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


@pytest.mark.asyncio
async def test_factory_routes_standard_deriv_markets():
    provider = get_market_data_provider("deriv", "EUR/USD")
    assert isinstance(provider, DerivMarketDataProvider)


@pytest.mark.asyncio
async def test_active_symbol_resolution_and_price(monkeypatch):
    provider = DerivMarketDataProvider()
    DerivMarketDataProvider._symbols_cache = None
    DerivMarketDataProvider._price_cache.clear()
    DerivMarketDataProvider._public_ws = None
    fake = FakeConnect(
        [
            [
                {
                    "msg_type": "active_symbols",
                    "active_symbols": [
                        {
                            "underlying_symbol": "frxEURUSD",
                            "underlying_symbol_name": "EUR/USD",
                            "underlying_symbol_type": "forex",
                            "market": "forex",
                            "pip_size": 0.0001,
                            "exchange_is_open": 1,
                            "is_trading_suspended": 0,
                        },
                        {
                            "underlying_symbol": "frxXAUUSD",
                            "underlying_symbol_name": "Gold/USD",
                            "underlying_symbol_type": "forex",
                            "market": "forex",
                            "pip_size": 0.01,
                            "exchange_is_open": 1,
                            "is_trading_suspended": 0,
                        },
                    ],
                }
            ],
            [
                {"msg_type": "tick", "tick": {"quote": "1.10234"}}
            ],
        ]
    )
    with patch("app.data_engine.providers.deriv.websockets.connect", fake):
        price = await provider.get_current_price("EUR/USD")
    assert price == pytest.approx(1.10234)


@pytest.mark.asyncio
async def test_candles_are_converted_and_sorted(monkeypatch):
    provider = DerivMarketDataProvider()
    DerivMarketDataProvider._public_ws = None
    DerivMarketDataProvider._symbols_cache = (
        9999999999.0,
        [
            {
                "underlying_symbol": "frxEURUSD",
                "display_name": "EUR/USD",
                "symbol": "frxEURUSD",
            }
        ],
    )
    fake = FakeConnect(
        [
            [
                {
                    "msg_type": "candles",
                    "candles": [
                        {"epoch": 1360, "open": "1.1", "high": "1.2", "low": "1.0", "close": "1.15"},
                        {"epoch": 1000, "open": "1.0", "high": "1.1", "low": "0.9", "close": "1.05"},
                    ],
                }
            ]
        ]
    )
    with patch("app.data_engine.providers.deriv.websockets.connect", fake):
        candles = await provider.get_candles("EUR/USD", "m5", 2)
    assert [c.timestamp for c in candles] == [
        datetime.fromtimestamp(1000, tz=timezone.utc),
        datetime.fromtimestamp(1360, tz=timezone.utc),
    ]
    assert candles[-1].close == pytest.approx(1.15)


def test_unsupported_instrument_is_rejected():
    provider = DerivMarketDataProvider()
    with pytest.raises(Exception):
        import asyncio
        asyncio.run(provider.get_current_price("BTC/USD"))
