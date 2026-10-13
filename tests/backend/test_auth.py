"""Comprehensive tests for authentication, tokens, and user profiles."""

from datetime import timedelta
from fastapi.testclient import TestClient

from app.core.security import create_jwt_token
from tests.backend.conftest import USER_A_ID, USER_A_EMAIL


def test_signup_validation_failures(client: TestClient) -> None:
    """Verify registration rejects passwords shorter than 8 chars and bad emails."""
    # 1. Password too short (< 8 chars)
    res1 = client.post(
        "/api/v1/auth/signup",
        json={"email": "student@college.edu", "password": "short"},
    )
    assert res1.status_code == 422
    data1 = res1.json()
    assert data1["error_code"] == "VALIDATION_ERROR"
    assert any("password" in str(item["field"]) for item in data1["validation_errors"])

    # 2. Invalid email format
    res2 = client.post(
        "/api/v1/auth/signup",
        json={"email": "not-an-email", "password": "ValidPassword123!"},
    )
    assert res2.status_code == 422
    data2 = res2.json()
    assert any("email" in str(item["field"]) for item in data2["validation_errors"])


def test_signup_success(client: TestClient) -> None:
    """Verify valid signup returns 201 and valid authentication tokens."""
    payload = {
        "email": "new.student@university.edu",
        "password": "StrongPassword2026!",
        "full_name": "New Student",
    }
    response = client.post("/api/v1/auth/signup", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert "user_id" in data
    assert data["email"] == "new.student@university.edu"


def test_login_invalid_password(client: TestClient) -> None:
    """Verify login with invalid password fails with HTTP 401."""
    payload = {
        "email": "student@college.edu",
        "password": "123",  # invalid
    }
    response = client.post("/api/v1/auth/login", json=payload)
    assert response.status_code == 401
    data = response.json()
    assert data["error_code"] == "UNAUTHORIZED"


def test_login_success(client: TestClient) -> None:
    """Verify login with valid credentials succeeds with HTTP 200."""
    payload = {
        "email": "student@college.edu",
        "password": "ValidPassword123!",
    }
    response = client.post("/api/v1/auth/login", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["email"] == "student@college.edu"


def test_protected_route_missing_token(client: TestClient) -> None:
    """Verify accessing protected /auth/me without token returns 401."""
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    data = response.json()
    assert data["error_code"] == "UNAUTHORIZED"
    assert "Missing HTTP Authorization Bearer token" in data["detail"]


def test_protected_route_expired_token(client: TestClient) -> None:
    """Verify accessing protected route with expired token returns 401."""
    expired_token = create_jwt_token(
        user_id=USER_A_ID,
        email=USER_A_EMAIL,
        expires_delta=timedelta(seconds=-60),  # expired 60 seconds ago
    )
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert response.status_code == 401
    data = response.json()
    assert data["error_code"] == "UNAUTHORIZED"
    assert "expired" in data["detail"].lower()


def test_protected_route_forged_or_malformed_token(client: TestClient) -> None:
    """Verify accessing protected route with forged signature returns 401."""
    forged_token = create_jwt_token(
        user_id=USER_A_ID,
        email=USER_A_EMAIL,
        secret_key="completely-wrong-unauthorized-secret-key",
    )
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {forged_token}"},
    )
    assert response.status_code == 401
    data = response.json()
    assert data["error_code"] == "UNAUTHORIZED"


def test_get_me_success(client: TestClient, user_a_headers: dict[str, str]) -> None:
    """Verify valid token retrieves authenticated profile and preferences."""
    response = client.get("/api/v1/auth/me", headers=user_a_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(USER_A_ID)
    assert data["email"] == USER_A_EMAIL
    assert "preferences" in data
    assert data["preferences"]["work_start_time"] == "09:00:00"
    assert data["preferences"]["work_end_time"] == "18:00:00"
    assert data["preferences"]["buffer_minutes"] == 15


def test_update_preferences_success(
    client: TestClient, user_a_headers: dict[str, str]
) -> None:
    """Verify updating preferences saves to database and returns updated values."""
    update_payload = {
        "work_start_time": "08:30:00",
        "work_end_time": "17:30:00",
        "buffer_minutes": 20,
        "max_focus_hours_per_day": 7,
    }
    response = client.put(
        "/api/v1/auth/preferences",
        json=update_payload,
        headers=user_a_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["work_start_time"] == "08:30:00"
    assert data["work_end_time"] == "17:30:00"
    assert data["buffer_minutes"] == 20
    assert data["max_focus_hours_per_day"] == 7

    # Verify subsequent GET /auth/me reflects the persisted updates
    get_res = client.get("/api/v1/auth/me", headers=user_a_headers)
    assert get_res.json()["preferences"]["buffer_minutes"] == 20


def test_logout(client: TestClient, user_a_headers: dict[str, str]) -> None:
    """Verify logout endpoint invalidates session cleanly."""
    response = client.post("/api/v1/auth/logout", headers=user_a_headers)
    assert response.status_code == 200
    assert "Successfully logged out" in response.json()["message"]
