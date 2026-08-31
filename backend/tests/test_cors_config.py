from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_cors_middleware_is_attached():
    assert any(m.cls.__name__ == "CORSMiddleware" for m in app.user_middleware)


def test_cors_allows_configured_origin():
    resp = client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_cors_rejects_unlisted_origin():
    resp = client.get("/health", headers={"Origin": "https://not-allowed.example.com"})
    # The request still succeeds server-side (CORS is enforced by the
    # browser, not the server) -- but no matching allow-origin header
    # is returned, so a real browser would block the response.
    assert resp.headers.get("access-control-allow-origin") != "https://not-allowed.example.com"


def test_cors_only_allows_get():
    from app.core.config import get_settings
    settings = get_settings()
    for m in app.user_middleware:
        if m.cls.__name__ == "CORSMiddleware":
            assert m.kwargs.get("allow_methods") == ["GET"]


def test_cors_does_not_allow_credentials():
    """No cookies/auth headers are passed cross-origin -- this API has
    no session/auth concept, and this keeps it that way explicitly."""
    for m in app.user_middleware:
        if m.cls.__name__ == "CORSMiddleware":
            assert m.kwargs.get("allow_credentials") is False
