"""
Tests for the integration-milestone API: /decisions, /strategy/select,
/instruments. All GET-only, all read-only, all built on top of
Phase 14's Selector and the persisted ValidatedStrategyConfig registry
— no new evidence, no new backtests, no path to execution.
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_decisions_endpoint_exists_and_returns_200():
    resp = client.get("/decisions", params={"instrument": "XAU/USD", "timeframe": "h1"})
    assert resp.status_code == 200


def test_decisions_response_schema_complete():
    resp = client.get("/decisions", params={"instrument": "XAU/USD", "timeframe": "h1"})
    body = resp.json()
    required_fields = {
        "instrument", "timeframe", "timestamp", "has_validated_edge", "selector_status",
        "selected_config", "research_gate_status", "final_decision", "reason",
        "regime_evidence", "considered_candidates", "research_recommendation",
    }
    assert required_fields <= set(body.keys())


def test_no_validated_edge_for_eurusd_real_data():
    resp = client.get("/decisions", params={"instrument": "EUR/USD", "timeframe": "h1"})
    body = resp.json()
    assert body["selector_status"] == "NO_VALIDATED_EDGE"
    assert body["has_validated_edge"] is False
    assert body["final_decision"] == "NO_TRADE"


def test_promising_not_tradeable_for_xauusd_real_data():
    resp = client.get("/decisions", params={"instrument": "XAU/USD", "timeframe": "h1"})
    body = resp.json()
    assert body["selector_status"] == "PROMISING_NOT_TRADEABLE"
    assert body["has_validated_edge"] is False
    assert body["final_decision"] == "NO_TRADE"
    assert body["final_decision"] != "PAPER_TRADE_APPROVED"
    assert body["final_decision"] != "LIVE_TRADE_APPROVED"


def test_no_research_at_all_for_unknown_instrument():
    resp = client.get("/decisions", params={"instrument": "BTC/USD", "timeframe": "h1"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["selector_status"] == "NO_VALIDATED_EDGE"


def test_invalid_timeframe_rejected():
    resp = client.get("/decisions", params={"instrument": "EUR/USD", "timeframe": "not_a_timeframe"})
    assert resp.status_code == 400


def test_missing_instrument_rejected():
    resp = client.get("/decisions", params={"timeframe": "h1"})
    assert resp.status_code == 422


def test_instrument_format_case_insensitive_timeframe():
    resp_lower = client.get("/decisions", params={"instrument": "XAU/USD", "timeframe": "h1"})
    resp_upper = client.get("/decisions", params={"instrument": "XAU/USD", "timeframe": "H1"})
    assert resp_lower.json()["selector_status"] == resp_upper.json()["selector_status"]


def test_final_decision_never_says_live():
    for instrument in ("EUR/USD", "GBP/USD", "XAU/USD", "USD/JPY"):
        resp = client.get("/decisions", params={"instrument": instrument, "timeframe": "h1"})
        assert "LIVE" not in resp.json()["final_decision"]


def test_strategy_select_endpoint():
    resp = client.get("/strategy/select", params={"instrument": "XAU/USD", "timeframe": "h1"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "PROMISING_NOT_TRADEABLE"


def test_instruments_endpoint_lists_real_researched_combinations():
    resp = client.get("/instruments")
    assert resp.status_code == 200
    body = resp.json()
    instruments = {item["instrument"] for item in body}
    assert "XAU/USD" in instruments
    assert "EUR/USD" in instruments


def test_deterministic_decisions_response():
    r1 = client.get("/decisions", params={"instrument": "XAU/USD", "timeframe": "h1"})
    r2 = client.get("/decisions", params={"instrument": "XAU/USD", "timeframe": "h1"})
    b1, b2 = r1.json(), r2.json()
    for key in ("selector_status", "has_validated_edge", "final_decision", "reason"):
        assert b1[key] == b2[key]


def test_all_new_routes_are_get_only():
    spec = app.openapi()
    for path in ("/decisions", "/strategy/select", "/instruments"):
        assert set(spec["paths"][path].keys()) <= {"get"}
