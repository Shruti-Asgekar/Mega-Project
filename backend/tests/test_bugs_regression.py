"""
Regression tests for Bug 1 (pipeline error handling & non-blocking execution)
and Bug 2 (fraud graph JSON format, in-memory caching, memory limits).
"""

import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.app.db import init_db
from backend.app.db.database import SessionLocal
from backend.app.db.models import Case, Applicant
from backend.app.modules.m7_fraudring import invalidate_graph_cache, _GRAPH_CACHE

@pytest.fixture(scope="module")
def client():
    init_db()
    with TestClient(app) as c:
        yield c

def test_api_error_returns_json_with_request_id(client):
    """Bug 1: Verify all /api/* error responses return valid JSON and include X-Request-ID."""
    # 404 error
    resp = client.get("/api/nonexistent-route-12345")
    assert resp.status_code == 404
    assert resp.headers.get("content-type", "").startswith("application/json")
    data = resp.json()
    assert "error" in data or "detail" in data
    assert "X-Request-ID" in resp.headers

    # 404 on specific entity
    resp = client.get("/api/cases/invalid-case-id-999")
    assert resp.status_code == 404
    assert resp.headers.get("content-type", "").startswith("application/json")
    data = resp.json()
    assert data.get("error") == "CASE_NOT_FOUND"

def test_case_creation_non_blocking_returns_202(client):
    """Bug 1: Verify POST /api/cases creates case and returns 202 Accepted with poll URL."""
    payload = {
        "applicant_name": "Suresh Raina",
        "phone": "9876500001",
        "address": "Flat 101, Brigade Metropolis, Whitefield, Bangalore",
        "consent_accepted": "true",
        "consent_version": "v1.0",
        "run_async": "true"
    }

    resp = client.post("/api/cases", data=payload)
    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "queued"
    assert "case_id" in data
    assert "poll_url" in data
    assert data["pipeline_status"] == "queued"

    case_id = data["case_id"]

    # Poll status endpoint
    status_resp = client.get(f"/api/cases/{case_id}/status")
    assert status_resp.status_code == 200
    sdata = status_resp.json()
    assert sdata["case_id"] == case_id
    assert "pipeline_status" in sdata
    assert "pipeline_step" in sdata

def test_graph_data_returns_json_and_caches(client):
    """Bug 2: Verify /api/graph/data returns Vis.js nodes/edges and caches in memory."""
    invalidate_graph_cache()
    assert _GRAPH_CACHE["data"] is None

    resp = client.get("/api/graph/data")
    assert resp.status_code == 200
    data = resp.json()

    assert "nodes" in data
    assert "edges" in data
    assert "ring_count" in data
    assert "summary" in data

    # Verify cache is populated
    assert _GRAPH_CACHE["data"] is not None

    # Invalidate and check cleared
    invalidate_graph_cache()
    assert _GRAPH_CACHE["data"] is None

def test_api_health_includes_memory_rss(client):
    """Bug 2: Verify /api/health includes memory_rss_mb metric for Render free-tier monitoring."""
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert "memory_rss_mb" in data
    assert isinstance(data["memory_rss_mb"], (int, float))
    assert data["memory_rss_mb"] > 0
    # On 512MB Render free tier, RSS should typically be < 300MB
    assert data["memory_rss_mb"] < 450
