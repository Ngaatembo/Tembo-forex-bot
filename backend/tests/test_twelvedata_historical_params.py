import pytest
from datetime import datetime, timezone

from app.core.config import get_settings
from app.data_engine.providers.twelvedata import TwelveDataProvider


@pytest.mark.asyncio
async def test_bounded_historical_request_omits_outputsize(monkeypatch):
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "twelvedata")
    monkeypatch.setenv("MARKET_DATA_API_KEY", "test-key")
    get_settings.cache_clear()

    provider = TwelveDataProvider()
    captured = {}

    async def fake_get(path, params):
        captured["path"] = path
        captured["params"] = params
        return {
            "values": [{
                "datetime": "2026-09-25 05:00:00",
                "open": "1.1000",
                "high": "1.1010",
                "low": "1.0990",
                "close": "1.1005",
                "volume": "",
            }]
        }

    monkeypatch.setattr(provider, "_get", fake_get)
    try:
        candles = await provider.get_historical_data(
            "EUR/USD",
            "h1",
            datetime(2026, 9, 25, 5, tzinfo=timezone.utc),
            datetime(2026, 9, 25, 6, tzinfo=timezone.utc),
        )
    finally:
        await provider._client.aclose()
        get_settings.cache_clear()

    assert len(candles) == 1
    assert captured["path"] == "/time_series"
    assert captured["params"]["start_date"] == "2026-09-25 05:00:00"
    assert captured["params"]["end_date"] == "2026-09-25 06:00:00"
    assert "outputsize" not in captured["params"]
