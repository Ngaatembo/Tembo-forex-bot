from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_news_endpoint_returns_demo_status_by_default():
    resp = client.get("/news")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] in ("DEMO", "LIVE", "UNAVAILABLE", "STALE", "CONFIRMED_NO_RELEVANT_NEWS")
    assert body["status"] == "DEMO"


def test_news_for_instrument_endpoint():
    resp = client.get("/news/EUR%2FUSD")
    assert resp.status_code == 200
    assert resp.json()["instrument"] == "EUR/USD"


def test_calendar_endpoint_returns_unavailable_for_mock():
    resp = client.get("/calendar")
    assert resp.status_code == 200
    assert resp.json()["status"] == "UNAVAILABLE"
    assert resp.json()["events"] == []


def test_calendar_for_currency_endpoint():
    resp = client.get("/calendar/USD")
    assert resp.status_code == 200
    assert resp.json()["currency"] == "USD"


def test_data_status_endpoint_reports_all_three_providers():
    resp = client.get("/system/data-status")
    assert resp.status_code == 200
    body = resp.json()
    assert "market_data" in body
    assert "news" in body
    assert "economic_calendar" in body
    assert body["news"]["provider"] == "mock"


def test_data_status_never_exposes_api_keys():
    resp = client.get("/system/data-status")
    body_str = str(resp.json())
    assert "api_key" not in body_str.lower()


def test_all_news_routes_are_get_only():
    spec = app.openapi()
    for path in ("/news", "/calendar", "/system/data-status"):
        assert set(spec["paths"][path].keys()) <= {"get"}


def test_decisions_endpoint_includes_news_and_macro_context():
    resp = client.get("/decisions", params={"instrument": "XAU/USD", "timeframe": "h1"})
    body = resp.json()
    assert "news_context" in body
    assert "macro_event_risk" in body
    assert body["macro_event_risk"]["level"] in ("HIGH", "MEDIUM", "LOW", "UNKNOWN")


def test_decisions_macro_risk_unknown_when_calendar_unavailable():
    resp = client.get("/decisions", params={"instrument": "XAU/USD", "timeframe": "h1"})
    assert resp.json()["macro_event_risk"]["level"] == "UNKNOWN"
