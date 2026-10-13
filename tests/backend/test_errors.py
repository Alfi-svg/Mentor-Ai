"""Tests for structured error envelopes and exception handling."""

from fastapi.testclient import TestClient


def test_404_error_envelope(client: TestClient) -> None:
    """Verify non-existent route returns standard ErrorResponse envelope."""
    response = client.get("/api/v1/non-existent-route")
    assert response.status_code == 404
    data = response.json()
    assert "status_code" in data
    assert data["status_code"] == 404
    assert data["error_code"] == "NOT_FOUND"
    assert "detail" in data
    assert "trace_id" in data
    assert "timestamp" in data


def test_error_envelope_structure_consistency(client: TestClient) -> None:
    """Verify error envelope contains all required fields."""
    response = client.get("/api/v1/not-found-endpoint")
    data = response.json()
    required_keys = {"status_code", "error_code", "detail", "trace_id", "timestamp"}
    assert required_keys.issubset(data.keys())
