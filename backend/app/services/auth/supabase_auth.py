"""Supabase Auth service handling sign up, login, logout, and token validation."""

import uuid

import httpx
from pydantic import BaseModel, EmailStr

from app.core.config import settings
from app.core.errors import AppException, UnauthorizedException
from app.core.logging import get_logger
from app.core.security import create_jwt_token

logger = get_logger("mentor_ai.supabase_auth")


class AuthTokenResponse(BaseModel):
    """Structured response from authentication operations."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int = 3600
    refresh_token: str | None = None
    user_id: uuid.UUID
    email: EmailStr


class SupabaseAuthService:
    """Service communicating with Supabase GoTrue Auth."""

    def __init__(self) -> None:
        self.supabase_url = settings.SUPABASE_URL.rstrip("/")
        self.anon_key = settings.SUPABASE_ANON_KEY
        self.is_live = settings.has_supabase_credentials

    def _get_headers(self, token: str | None = None) -> dict[str, str]:
        headers = {
            "apikey": self.anon_key,
            "Content-Type": "application/json",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    async def sign_up(
        self, email: str, password: str, full_name: str | None = None
    ) -> AuthTokenResponse:
        """Register a new user with Supabase Auth."""
        if not self.is_live:
            # Deterministic local test mode when Supabase project is not yet configured
            logger.info("Using local test mode for signup (Supabase unconfigured)", email=email)
            deterministic_id = uuid.uuid5(uuid.NAMESPACE_DNS, f"mentor-ai-{email}")
            token = create_jwt_token(user_id=deterministic_id, email=email)
            return AuthTokenResponse(
                access_token=token,
                refresh_token="local-test-refresh-token",  # noqa: S106
                user_id=deterministic_id,
                email=email,
            )

        url = f"{self.supabase_url}/auth/v1/signup"
        payload = {
            "email": email,
            "password": password,
            "data": {"full_name": full_name} if full_name else {},
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.post(url, json=payload, headers=self._get_headers())
                if response.status_code >= 400:
                    data = response.json()
                    detail = data.get("msg") or data.get("error_description") or "Sign up failed."
                    raise AppException(detail=detail, status_code=response.status_code)

                data = response.json()
                user_data = data.get("user") or {}
                user_id = uuid.UUID(user_data.get("id"))
                access_token = data.get("access_token")

                # If email confirmation is enabled, Supabase may not return access_token immediately
                if not access_token:
                    access_token = create_jwt_token(user_id=user_id, email=email)

                return AuthTokenResponse(
                    access_token=access_token,
                    refresh_token=data.get("refresh_token"),
                    user_id=user_id,
                    email=email,
                )
            except httpx.RequestError as exc:
                logger.error("Supabase Auth connection error during sign up", error=str(exc))
                raise AppException(
                    detail="Unable to reach authentication service.", status_code=503
                ) from exc

    async def sign_in(self, email: str, password: str) -> AuthTokenResponse:
        """Authenticate user with email and password via Supabase Auth."""
        if not self.is_live:
            # Deterministic local test mode verification
            logger.info("Using local test mode for login (Supabase unconfigured)", email=email)
            if len(password) < 6:
                raise UnauthorizedException(detail="Invalid login credentials.")
            deterministic_id = uuid.uuid5(uuid.NAMESPACE_DNS, f"mentor-ai-{email}")
            token = create_jwt_token(user_id=deterministic_id, email=email)
            return AuthTokenResponse(
                access_token=token,
                refresh_token="local-test-refresh-token",  # noqa: S106
                user_id=deterministic_id,
                email=email,
            )

        url = f"{self.supabase_url}/auth/v1/token?grant_type=password"
        payload = {"email": email, "password": password}

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.post(url, json=payload, headers=self._get_headers())
                if response.status_code >= 400:
                    data = response.json()
                    detail = (
                        data.get("msg") or data.get("error_description") or "Invalid credentials."
                    )
                    raise UnauthorizedException(detail=detail)

                data = response.json()
                user_data = data.get("user") or {}
                user_id = uuid.UUID(user_data.get("id"))

                return AuthTokenResponse(
                    access_token=data["access_token"],
                    refresh_token=data.get("refresh_token"),
                    user_id=user_id,
                    email=email,
                )
            except httpx.RequestError as exc:
                logger.error("Supabase Auth connection error during sign in", error=str(exc))
                raise AppException(
                    detail="Unable to reach authentication service.", status_code=503
                ) from exc

    async def sign_out(self, access_token: str) -> bool:
        """Invalidate session in Supabase Auth."""
        if not self.is_live:
            return True

        url = f"{self.supabase_url}/auth/v1/logout"
        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                response = await client.post(url, headers=self._get_headers(token=access_token))
                return response.status_code < 400
            except Exception as exc:
                logger.warning("Supabase logout call failed", error=str(exc))
                return False
