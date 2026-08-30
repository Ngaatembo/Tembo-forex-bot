from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_candidates_endpoint_returns_real_reconstructed_data():
    resp = client.get("/research/candidates")
    assert resp.status_code == 200
    candidates = resp.json()
    assert len(candidates) == 5
    names = {c["name"] for c in candidates}
    assert "H1 — Range-Extreme Mean Reversion" in names
    assert any("lookback=20" in n for n in names)


def test_candidate_by_id_returns_full_record():
    all_candidates = client.get("/research/candidates").json()
    h1 = next(c for c in all_candidates if "H1" in c["name"])
    resp = client.get(f"/research/candidates/{h1['candidate_id']}")
    assert resp.status_code == 200
    assert resp.json()["verdict"] == "OUT_OF_SAMPLE_FAILED"
    assert resp.json()["gate_status"] == "CLOSED"


def test_candidate_by_id_404_for_unknown_id():
    resp = client.get("/research/candidates/cand_does_not_exist")
    assert resp.status_code == 404


def test_families_endpoint_reflects_real_saturation():
    resp = client.get("/research/families")
    assert resp.status_code == 200
    families = {f["family"]: f for f in resp.json()}
    assert "breakout" in families
    # 3 breakout candidates, all REJECTED -> 100% negative, still below
    # the min-hypotheses-for-saturation default of 3... exactly 3, so it IS saturated
    assert families["breakout"]["hypothesis_count"] == 3
    assert families["breakout"]["rejected_count"] == 3
    assert families["breakout"]["saturation_status"] == "SATURATED"


def test_all_research_routes_are_get_only():
    """Structural proof, not just convention — matches the existing
    test_research_security_boundary.py pattern for this router."""
    spec = app.openapi()
    for path, methods in spec["paths"].items():
        if path.startswith("/research"):
            assert set(methods.keys()) <= {"get"}, f"{path} exposes a non-GET method: {methods.keys()}"
