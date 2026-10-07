"""API smoke tests (no model required: LLM and RAG loading are disabled in conftest)."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client(seeded_db):
    from app.main import create_app

    with TestClient(create_app()) as c:
        yield c


def test_health_reports_components(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert set(r.json()["components"]) >= {"llm", "rag"}


def test_chat_returns_503_when_model_not_loaded(client):
    r = client.post("/api/chat", json={"message": "What is an ERA?"})
    assert r.status_code == 503


def test_chat_input_validation(client):
    assert client.post("/api/chat", json={"message": "   "}).status_code == 422
    assert client.post("/api/chat", json={"message": "x" * 2001}).status_code == 422


def test_kpis_endpoint(client):
    r = client.get("/api/kpis", params={"start_date": "2026-07-01", "end_date": "2026-09-30"})
    assert r.status_code == 200
    assert len(r.json()["kpis"]) >= 8


def test_overview_endpoint(client):
    body = client.get("/api/analytics/overview").json()
    for key in ("kpis", "claims_over_time", "payments_over_time", "ar_over_time", "status_distribution", "payers"):
        assert key in body


def test_invalid_filters_rejected(client):
    assert client.get("/api/kpis", params={"status": "bogus"}).status_code == 422
    assert client.get("/api/kpis", params={"start_date": "2026-09-01", "end_date": "2026-01-01"}).status_code == 422
    assert client.get("/api/kpis", params={"payer_id": "x;drop table"}).status_code == 422


def test_claims_list_and_detail(client):
    page = client.get("/api/claims", params={"page_size": 5, "status": "denied"}).json()
    assert page["total"] > 0 and len(page["items"]) == 5
    assert all(i["status"] == "denied" for i in page["items"])
    cid = page["items"][0]["claim_id"]
    detail = client.get(f"/api/claims/{cid}").json()
    assert detail["claim_id"] == cid
    assert detail["patient"]["synthetic"] is True
    assert detail["denials"], "denied claim should carry denial records"


def test_claim_not_found_and_bad_id(client):
    assert client.get("/api/claims/CLM-999999").status_code == 404
    assert client.get("/api/claims/not-a-claim").status_code == 422
