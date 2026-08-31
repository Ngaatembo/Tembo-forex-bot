from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_account_overview_returns_real_snapshot_data():
    resp = client.get("/account/overview")
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "PAPER_ONLY"
    assert body["real_money"] == 0
    assert body["initial_equity"] == 10000.0


def test_open_positions_endpoint():
    resp = client.get("/positions/open")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_closed_positions_endpoint_has_real_trade():
    resp = client.get("/positions/closed")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) >= 1
    assert body[0]["exit_reason"] == "STOP_LOSS"


def test_risk_metrics_endpoint():
    resp = client.get("/risk/metrics")
    assert resp.status_code == 200
    body = resp.json()
    assert body["limits"]["max_risk_per_trade_pct"] == 0.01


def test_performance_endpoint_computed_from_real_trades():
    resp = client.get("/performance")
    assert resp.status_code == 200
    body = resp.json()
    assert body["trade_count"] >= 1
    assert "win_rate" in body


def test_events_endpoint_includes_scenario_decisions():
    resp = client.get("/events")
    assert resp.status_code == 200
    body = resp.json()
    statuses = {e.get("status") for e in body if e["type"] == "DECISION"}
    assert "NO_VALIDATED_EDGE" in statuses
    assert "PAPER_TRADE_APPROVED" in statuses


def test_all_paper_trading_routes_are_get_only():
    spec = app.openapi()
    for path in ("/account/overview", "/positions/open", "/positions/closed", "/risk/metrics", "/performance", "/events"):
        assert set(spec["paths"][path].keys()) <= {"get"}, f"{path} exposes a non-GET method"


def test_no_write_endpoint_exists_for_opening_a_paper_trade():
    spec = app.openapi()
    suspicious = [p for p in spec["paths"] if "open" in p.lower() and "get" not in spec["paths"][p]]
    assert suspicious == []
