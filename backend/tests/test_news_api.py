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


def test_calendar_endpoint_exposes_error_detail_when_unavailable():
    """New: mirrors /news's existing 'error' field -- so a future
    UNAVAILABLE state is diagnosable, not a silent black box."""
    resp = client.get("/calendar")
    body = resp.json()
    assert "error" in body
    assert body["error"] is not None
    assert "ECONOMIC_CALENDAR_PROVIDER" in body["error"]


def test_calendar_reports_static_official_not_live(monkeypatch):
    from app.core.config import get_settings
    get_settings.cache_clear()
    monkeypatch.setenv("ECONOMIC_CALENDAR_PROVIDER", "static_central_banks")
    import app.news_engine.context as context_module
    context_module._calendar_cache._store.clear()

    resp = client.get("/calendar")
    body = resp.json()
    assert body["status"] == "STATIC_OFFICIAL"
    assert body["status"] != "LIVE"
    assert len(body["events"]) == 32
    get_settings.cache_clear()
    context_module._calendar_cache._store.clear()


def test_calendar_for_currency_reports_static_official(monkeypatch):
    from app.core.config import get_settings
    get_settings.cache_clear()
    monkeypatch.setenv("ECONOMIC_CALENDAR_PROVIDER", "static_central_banks")
    import app.news_engine.context as context_module
    context_module._calendar_cache._store.clear()

    resp = client.get("/calendar/USD")
    body = resp.json()
    assert body["status"] == "STATIC_OFFICIAL"
    assert len(body["events"]) == 8
    get_settings.cache_clear()
    context_module._calendar_cache._store.clear()


def test_calendar_events_include_time_confirmed_field(monkeypatch):
    from app.core.config import get_settings
    get_settings.cache_clear()
    monkeypatch.setenv("ECONOMIC_CALENDAR_PROVIDER", "static_central_banks")
    import app.news_engine.context as context_module
    context_module._calendar_cache._store.clear()

    resp = client.get("/calendar/GBP")
    body = resp.json()
    assert all(e["time_confirmed"] is False for e in body["events"])
    get_settings.cache_clear()
    context_module._calendar_cache._store.clear()


def test_calendar_shows_events_earlier_in_the_year_not_just_forward_from_now(monkeypatch):
    """Regression test for a real bug found during Phase 1: a static
    dataset's earlier-in-the-year events were invisible once 'now' had
    passed them, because /calendar only looked forward. All 32 events
    must be visible regardless of today's date within the covered year."""
    from app.core.config import get_settings
    get_settings.cache_clear()
    monkeypatch.setenv("ECONOMIC_CALENDAR_PROVIDER", "static_central_banks")
    import app.news_engine.context as context_module
    context_module._calendar_cache._store.clear()

    resp = client.get("/calendar")
    body = resp.json()
    assert len(body["events"]) == 32
    get_settings.cache_clear()
    context_module._calendar_cache._store.clear()
