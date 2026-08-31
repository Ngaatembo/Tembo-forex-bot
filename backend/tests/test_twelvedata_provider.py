"""
Tests for TwelveDataProvider. All HTTP calls are mocked -- these never
touch the real network or depend on Twelve Data being online. The
separate real connectivity test (scripts/test_twelvedata_connectivity.py)
covers the actual live check.
"""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.data_engine.market_data import get_market_data_provider


@pytest.fixture
def provider(monkeypatch):
    from app.core.config import get_settings
    get_settings.cache_clear()
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "twelvedata")
    monkeypatch.setenv("MARKET_DATA_API_KEY", "fake_test_key_never_real")
    from app.data_engine.providers.twelvedata import TwelveDataProvider
    p = TwelveDataProvider()
    yield p
    get_settings.cache_clear()


def mock_response(status_code, json_data):
    return httpx.Response(status_code, json=json_data, request=httpx.Request("GET", "https://api.twelvedata.com/x"))


def test_provider_requires_api_key(monkeypatch):
    from app.core.config import get_settings
    get_settings.cache_clear()
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "twelvedata")
    monkeypatch.delenv("MARKET_DATA_API_KEY", raising=False)
    from app.data_engine.providers.twelvedata import TwelveDataProvider
    with pytest.raises(ValueError):
        TwelveDataProvider()
    get_settings.cache_clear()


def test_factory_constructs_twelvedata_provider(provider):
    from app.data_engine.providers.twelvedata import TwelveDataProvider
    result = get_market_data_provider("twelvedata")
    assert isinstance(result, TwelveDataProvider)


def test_symbol_passthrough_matches_tembo_convention(provider):
    assert provider._to_provider_symbol("EUR/USD") == "EUR/USD"
    assert provider._to_provider_symbol("XAU/USD") == "XAU/USD"


def test_timeframe_mapping_matches_real_twelvedata_intervals(provider):
    assert provider._to_provider_interval("m5") == "5min"
    assert provider._to_provider_interval("m15") == "15min"
    assert provider._to_provider_interval("h1") == "1h"
    assert provider._to_provider_interval("h4") == "4h"
    assert provider._to_provider_interval("d1") == "1day"


def test_unsupported_timeframe_raises_explicit_error(provider):
    from app.data_engine.providers.twelvedata import UnsupportedTimeframeError
    with pytest.raises(UnsupportedTimeframeError):
        provider._to_provider_interval("m1")


def test_unsupported_instrument_raises_explicit_error(provider):
    from app.data_engine.providers.twelvedata import UnsupportedInstrumentError
    with pytest.raises(UnsupportedInstrumentError):
        provider._to_provider_symbol("BTC/USD")


@pytest.mark.asyncio
async def test_get_current_price_success(provider):
    fake_resp = mock_response(200, {"price": "1.10234"})
    with patch.object(provider._client, "get", new=AsyncMock(return_value=fake_resp)):
        price = await provider.get_current_price("EUR/USD")
    assert price == pytest.approx(1.10234)


@pytest.mark.asyncio
async def test_get_current_price_xauusd(provider):
    fake_resp = mock_response(200, {"price": "1923.45"})
    with patch.object(provider._client, "get", new=AsyncMock(return_value=fake_resp)):
        price = await provider.get_current_price("XAU/USD")
    assert price == pytest.approx(1923.45)


@pytest.mark.asyncio
async def test_get_candles_normalizes_string_values_to_floats(provider):
    fake_body = {
        "meta": {"symbol": "EUR/USD", "interval": "1h"},
        "values": [
            {"datetime": "2026-01-01 01:00:00", "open": "1.1000", "high": "1.1050", "low": "1.0990", "close": "1.1020", "volume": "0"},
            {"datetime": "2026-01-01 00:00:00", "open": "1.0980", "high": "1.1010", "low": "1.0970", "close": "1.1000", "volume": "0"},
        ],
        "status": "ok",
    }
    fake_resp = mock_response(200, fake_body)
    with patch.object(provider._client, "get", new=AsyncMock(return_value=fake_resp)):
        candles = await provider.get_candles("EUR/USD", "h1", limit=2)
    assert len(candles) == 2
    assert all(isinstance(c.open, float) for c in candles)
    assert candles[0].close == pytest.approx(1.1000)


@pytest.mark.asyncio
async def test_get_candles_malformed_response_raises_explicit_error(provider):
    from app.data_engine.providers.twelvedata import MalformedResponseError
    fake_resp = mock_response(200, {"unexpected": "shape"})
    with patch.object(provider._client, "get", new=AsyncMock(return_value=fake_resp)):
        with pytest.raises(MalformedResponseError):
            await provider.get_candles("EUR/USD", "h1")


@pytest.mark.asyncio
async def test_authentication_error_raises_explicit_exception(provider):
    from app.data_engine.providers.twelvedata import AuthenticationError
    fake_resp = mock_response(401, {"code": 401, "message": "Invalid apikey", "status": "error"})
    with patch.object(provider._client, "get", new=AsyncMock(return_value=fake_resp)):
        with pytest.raises(AuthenticationError):
            await provider.get_current_price("EUR/USD")


@pytest.mark.asyncio
async def test_rate_limit_error_raises_explicit_exception(provider):
    from app.data_engine.providers.twelvedata import RateLimitError
    fake_resp = mock_response(429, {"code": 429, "message": "Too many requests", "status": "error"})
    with patch.object(provider._client, "get", new=AsyncMock(return_value=fake_resp)):
        with pytest.raises(RateLimitError):
            await provider.get_current_price("EUR/USD")


@pytest.mark.asyncio
async def test_timeout_raises_explicit_exception(provider):
    from app.data_engine.providers.twelvedata import ProviderTimeoutError
    with patch.object(provider._client, "get", new=AsyncMock(side_effect=httpx.TimeoutException("timed out"))):
        with pytest.raises(ProviderTimeoutError):
            await provider.get_current_price("EUR/USD")


@pytest.mark.asyncio
async def test_network_failure_raises_explicit_exception(provider):
    from app.data_engine.providers.twelvedata import ProviderConnectionError
    with patch.object(provider._client, "get", new=AsyncMock(side_effect=httpx.ConnectError("dns failed"))):
        with pytest.raises(ProviderConnectionError):
            await provider.get_current_price("EUR/USD")


@pytest.mark.asyncio
async def test_instrument_metadata_xauusd_distinct_pip_size(provider):
    meta = await provider.get_instrument_metadata("XAU/USD")
    eur_meta = await provider.get_instrument_metadata("EUR/USD")
    assert meta.pip_size != eur_meta.pip_size


def test_api_key_never_appears_in_exception_messages(provider):
    from app.data_engine.providers.twelvedata import AuthenticationError
    err = AuthenticationError("some message", api_key=provider._api_key)
    assert provider._api_key not in str(err)


def test_api_key_never_appears_in_repr(provider):
    assert provider._api_key not in repr(provider)
    assert provider._api_key not in str(provider)
