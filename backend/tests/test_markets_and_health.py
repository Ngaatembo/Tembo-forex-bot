from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_markets_endpoint_with_mock_provider_returns_data():
    resp = client.get("/markets/EUR%2FUSD")
    assert resp.status_code == 200
    body = resp.json()
    assert body["instrument"] == "EUR/USD"
    assert body["provider"] == "mock"
    assert "current_price" in body
    assert "data_quality" in body


def test_markets_endpoint_url_decodes_instrument():
    resp = client.get("/markets/XAU%2FUSD")
    assert resp.status_code == 200
    assert resp.json()["instrument"] == "XAU/USD"


def test_markets_endpoint_invalid_timeframe_rejected():
    resp = client.get("/markets/EUR%2FUSD", params={"timeframe": "not_real"})
    assert resp.status_code == 400


def test_markets_endpoint_includes_data_quality_from_validator():
    resp = client.get("/markets/EUR%2FUSD")
    dq = resp.json()["data_quality"]
    assert "is_clean" in dq
    assert "ohlc_violations" in dq


def test_markets_route_is_get_only():
    spec = app.openapi()
    assert set(spec["paths"]["/markets/{instrument}"].keys()) <= {"get"}


def test_health_reports_mock_when_provider_is_mock():
    resp = client.get("/health")
    body = resp.json()
    assert body["market_data"] in ("mock", "configured", "available", "unavailable")
    assert body["market_data"] == "mock"


def test_health_reports_unavailable_when_provider_set_but_no_key(monkeypatch):
    from app.core.config import get_settings
    get_settings.cache_clear()
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "twelvedata")
    monkeypatch.delenv("MARKET_DATA_API_KEY", raising=False)
    resp = client.get("/health")
    assert resp.json()["market_data"] == "unavailable"
    get_settings.cache_clear()


def test_health_never_exposes_api_key():
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert "market_data_api_key" not in body
