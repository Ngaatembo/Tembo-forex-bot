from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_root():
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert "name" in body
    assert body["live_execution_enabled"] is False


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["live_execution_enabled"] is False
    assert body["paper_broker"] == "available"
