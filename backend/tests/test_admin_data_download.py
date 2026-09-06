"""
Tests for the temporary admin-only research-data download endpoint
(Experiment 3). Strictly read-only. No directory listing. Filenames
are checked against a hardcoded allowlist -- path traversal is
structurally impossible, not just filtered, since only an exact
allowlist match is ever accepted regardless of what string is sent.
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

VALID_TOKEN = "test_admin_token_never_real"


def _set_token(monkeypatch, token=VALID_TOKEN):
    from app.core.config import get_settings
    get_settings.cache_clear()
    monkeypatch.setenv("ADMIN_DOWNLOAD_TOKEN", token)


def _clear_token(monkeypatch):
    from app.core.config import get_settings
    get_settings.cache_clear()
    monkeypatch.delenv("ADMIN_DOWNLOAD_TOKEN", raising=False)


def test_endpoint_fails_closed_when_no_token_configured(monkeypatch):
    _clear_token(monkeypatch)
    resp = client.get("/admin/research-data/EURUSD_H1_2023plus.csv", headers={"Authorization": "Bearer anything"})
    assert resp.status_code in (403, 503)
    from app.core.config import get_settings
    get_settings.cache_clear()


def test_missing_authorization_header_rejected(monkeypatch):
    _set_token(monkeypatch)
    resp = client.get("/admin/research-data/EURUSD_H1_2023plus.csv")
    assert resp.status_code in (401, 403)
    from app.core.config import get_settings
    get_settings.cache_clear()


def test_wrong_token_rejected(monkeypatch):
    _set_token(monkeypatch)
    resp = client.get("/admin/research-data/EURUSD_H1_2023plus.csv", headers={"Authorization": "Bearer wrong_token"})
    assert resp.status_code == 401
    from app.core.config import get_settings
    get_settings.cache_clear()


def test_correct_token_but_missing_file_returns_404_not_fabricated(monkeypatch, tmp_path):
    _set_token(monkeypatch)
    from app.api.routes import admin_data
    original_dir = admin_data.DATA_DIR
    admin_data.DATA_DIR = str(tmp_path)
    try:
        resp = client.get("/admin/research-data/EURUSD_H1_2023plus.csv", headers={"Authorization": f"Bearer {VALID_TOKEN}"})
        assert resp.status_code == 404
    finally:
        admin_data.DATA_DIR = original_dir
    from app.core.config import get_settings
    get_settings.cache_clear()


def test_correct_token_and_existing_file_succeeds(monkeypatch, tmp_path):
    _set_token(monkeypatch)
    from app.api.routes import admin_data
    original_dir = admin_data.DATA_DIR
    admin_data.DATA_DIR = str(tmp_path)
    (tmp_path / "EURUSD_H1_2023plus.csv").write_text("timestamp,open,high,low,close,volume\n")
    try:
        resp = client.get("/admin/research-data/EURUSD_H1_2023plus.csv", headers={"Authorization": f"Bearer {VALID_TOKEN}"})
        assert resp.status_code == 200
        assert "timestamp" in resp.text
    finally:
        admin_data.DATA_DIR = original_dir
    from app.core.config import get_settings
    get_settings.cache_clear()


def test_all_expected_allowlisted_filenames_are_present():
    from app.api.routes.admin_data import ALLOWED_FILENAMES
    expected = {
        "EURUSD_H1_2023plus.csv", "GBPUSD_H1_2023plus.csv", "XAUUSD_H1_2023plus.csv",
        "EURUSD_H1_2023plus_metadata.json", "GBPUSD_H1_2023plus_metadata.json", "XAUUSD_H1_2023plus_metadata.json",
        "export_summary.json",
    }
    assert expected <= ALLOWED_FILENAMES


def test_path_traversal_attempts_rejected(monkeypatch):
    _set_token(monkeypatch)
    traversal_attempts = [
        "../../../etc/passwd", "..%2F..%2F..%2Fetc%2Fpasswd", "....//....//etc/passwd",
        "/etc/passwd", "EURUSD_H1_2023plus.csv/../../../etc/passwd",
    ]
    for attempt in traversal_attempts:
        resp = client.get(f"/admin/research-data/{attempt}", headers={"Authorization": f"Bearer {VALID_TOKEN}"})
        assert resp.status_code in (403, 404), f"traversal attempt {attempt!r} was not rejected (got {resp.status_code})"
    from app.core.config import get_settings
    get_settings.cache_clear()


def test_filename_not_in_allowlist_rejected(monkeypatch):
    _set_token(monkeypatch)
    resp = client.get("/admin/research-data/some_other_file.csv", headers={"Authorization": f"Bearer {VALID_TOKEN}"})
    assert resp.status_code == 403
    from app.core.config import get_settings
    get_settings.cache_clear()


def test_route_is_get_only():
    spec = app.openapi()
    matching = [p for p in spec["paths"] if "admin/research-data" in p]
    assert matching, "expected the admin research-data route to exist"
    for p in matching:
        assert set(spec["paths"][p].keys()) <= {"get"}


def test_token_never_appears_in_response_body(monkeypatch, tmp_path):
    _set_token(monkeypatch)
    from app.api.routes import admin_data
    original_dir = admin_data.DATA_DIR
    admin_data.DATA_DIR = str(tmp_path)
    (tmp_path / "export_summary.json").write_text('{"ok": true}')
    try:
        resp = client.get("/admin/research-data/export_summary.json", headers={"Authorization": f"Bearer {VALID_TOKEN}"})
        assert VALID_TOKEN not in resp.text
    finally:
        admin_data.DATA_DIR = original_dir
    from app.core.config import get_settings
    get_settings.cache_clear()
