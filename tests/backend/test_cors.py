"""Tests for safe CORS configuration."""

from fastapi.testclient import TestClient


def test_cors_allowed_origin(client: TestClient) -> None:
    """Allowed origin receives Access-Control-Allow-Origin header."""
    response = client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert (
        response.headers.get("access-control-allow-origin") == "http://localhost:3000"
    )


def test_cors_disallowed_origin(client: TestClient) -> None:
    """Disallowed origin does NOT receive Access-Control-Allow-Origin header."""
    response = client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://malicious-site.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    # When origin is rejected by CORSMiddleware, Access-Control-Allow-Origin is omitted
    assert response.headers.get("access-control-allow-origin") is None
