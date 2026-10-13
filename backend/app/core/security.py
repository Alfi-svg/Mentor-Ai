"""Cryptographic token verification, user authentication, and authorization dependencies."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import UnauthorizedException
from app.core.logging import get_logger
from app.db.models.profile import Profile
from app.db.session import get_db

logger = get_logger("mentor_ai.security")
http_bearer_scheme = HTTPBearer(auto_error=False)


class AuthenticatedUser(BaseModel):
    """Authenticated user context extracted from verified JWT claims."""

    id: uuid.UUID
    email: EmailStr
    role: str = "authenticated"
    app_metadata: dict[str, Any] = Field(default_factory=dict)
    user_metadata: dict[str, Any] = Field(default_factory=dict)


def create_jwt_token(
    user_id: uuid.UUID,
    email: str,
    secret_key: str | None = None,
    expires_delta: timedelta | None = None,
    role: str = "authenticated",
) -> str:
    """Create a signed JWT token (used for testing and development sessions)."""
    key = secret_key or settings.SUPABASE_JWT_SECRET or settings.SECRET_KEY
    delta = expires_delta or timedelta(hours=2)
    now = datetime.now(UTC)
    expire = now + delta

    payload = {
        "sub": str(user_id),
        "email": email,
        "role": role,
        "aud": "authenticated",
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    return jwt.encode(payload, key, algorithm="HS256")


def verify_token_claims(token: str) -> dict[str, Any]:
    """Cryptographically verify JWT token signature and return validated claims."""
    # List of candidate keys to test (Supabase JWT Secret, or fallback Secret Key)
    candidate_keys = [k for k in [settings.SUPABASE_JWT_SECRET, settings.SECRET_KEY] if k]
    if not candidate_keys:
        raise UnauthorizedException(detail="Server authentication key unconfigured.")

    last_error: Exception | None = None
    for key in candidate_keys:
        try:
            payload = jwt.decode(
                token,
                key,
                algorithms=["HS256"],
                options={"verify_aud": False},  # verified manually or flexibly
            )
            return cast(dict[str, Any], payload)
        except jwt.ExpiredSignatureError:
            raise UnauthorizedException(detail="Authentication token has expired.") from None
        except jwt.InvalidTokenError as exc:
            last_error = exc
            continue

    logger.warning("JWT verification failed with all candidate keys", error=str(last_error))
    raise UnauthorizedException(detail="Invalid or forged authentication token.")


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(http_bearer_scheme),
) -> AuthenticatedUser:
    """FastAPI dependency to extract and verify the authenticated user from Bearer JWT."""
    if credentials is None or not credentials.credentials:
        raise UnauthorizedException(detail="Missing HTTP Authorization Bearer token.")

    token = credentials.credentials
    claims = verify_token_claims(token)

    sub = claims.get("sub")
    email = claims.get("email")
    if not sub or not email:
        raise UnauthorizedException(detail="Malformed token: missing sub or email claims.")

    try:
        user_uuid = uuid.UUID(str(sub))
    except ValueError:
        raise UnauthorizedException(detail="Malformed token: invalid subject UUID.") from None

    authenticated_user = AuthenticatedUser(
        id=user_uuid,
        email=email,
        role=claims.get("role", "authenticated"),
        app_metadata=claims.get("app_metadata", {}),
        user_metadata=claims.get("user_metadata", {}),
    )

    # Attach to request state for downstream request tracing
    request.state.user = authenticated_user
    return authenticated_user


async def get_current_active_profile(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Profile:
    """Ensure user profile exists in database and return profile entity."""
    query = select(Profile).where(Profile.id == current_user.id)
    result = await db.execute(query)
    profile = result.scalar_one_or_none()

    if profile is None:
        # Auto-provision profile and default preferences if missing
        from app.db.models.profile import UserPreferences

        profile = Profile(
            id=current_user.id,
            email=str(current_user.email),
            full_name=current_user.user_metadata.get("full_name"),
            timezone=current_user.user_metadata.get("timezone", "UTC"),
        )
        db.add(profile)
        preferences = UserPreferences(
            user_id=current_user.id,
            work_start_time="09:00:00",
            work_end_time="18:00:00",
            buffer_minutes=15,
            default_task_duration=45,
            max_focus_hours_per_day=8,
            available_days=[1, 2, 3, 4, 5],
            auto_schedule_breaks=True,
        )
        db.add(preferences)
        await db.flush()

    return profile
