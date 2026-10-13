"""Unit & Integration tests for health and readiness endpoints."""

from fastapi.testclient import TestClient


def test_root_endpoint(client: TestClient) -> None:
    """Verify root status endpoint returns application metadata."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "name" in data
    assert "version" in data
    assert "docs_url" in data
    assert "health_url" in data
    assert data["name"] == "Mentor AI API"


def test_health_liveness_endpoint(client: TestClient) -> None:
    """Verify /api/v1/health returns healthy liveness status."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "version" in data
    assert "environment" in data
    assert "ai_provider" in data
    assert "timestamp" in data


def test_health_readiness_endpoint(client: TestClient) -> None:
    """Verify /api/v1/health/ready truthfully reports dependency readiness."""
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert "database" in data
    assert "ai_service" in data
    assert "details" in data
    assert "timestamp" in data


def test_response_headers_contain_trace_id(client: TestClient) -> None:
    """Verify that response headers include X-Request-ID and X-Response-Time-Ms."""
    response = client.get(
        "/api/v1/health", headers={"X-Request-ID": "test-trace-12345"}
    )
    assert response.status_code == 200
    assert response.headers.get("X-Request-ID") == "test-trace-12345"
    assert "X-Response-Time-Ms" in response.headers
