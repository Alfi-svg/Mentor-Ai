"""Authentication and user profile endpoints."""

import uuid

from fastapi import APIRouter, Depends, Header, status
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limit import rate_limit
from app.core.security import AuthenticatedUser, get_current_active_profile, get_current_user
from app.db.models.profile import Profile
from app.db.session import get_db
from app.services.auth.supabase_auth import AuthTokenResponse, SupabaseAuthService

router = APIRouter(prefix="/auth", tags=["auth"])
auth_service = SupabaseAuthService()


# -----------------------------------------------------------------------------
# Request & Response Schemas
# -----------------------------------------------------------------------------
class SignUpRequest(BaseModel):
    """Registration request schema."""

    email: EmailStr
    password: str = Field(min_length=8, description="Password must be at least 8 characters")
    full_name: str | None = Field(default=None, max_length=100)


class LoginRequest(BaseModel):
    """Login request schema."""

    email: EmailStr
    password: str = Field(min_length=1)


class PreferencesResponse(BaseModel):
    """User scheduling preferences representation."""

    work_start_time: str
    work_end_time: str
    buffer_minutes: int
    default_task_duration: int
    max_focus_hours_per_day: int
    available_days: list[int]
    auto_schedule_breaks: bool
    timezone: str = "UTC"


class UserProfileResponse(BaseModel):
    """Authenticated user profile representation."""

    id: uuid.UUID
    email: EmailStr
    full_name: str | None = None
    timezone: str
    preferences: PreferencesResponse | None = None


class PreferencesUpdateRequest(BaseModel):
    """Preferences update request schema."""

    work_start_time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}(:\d{2})?$")
    work_end_time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}(:\d{2})?$")
    buffer_minutes: int | None = Field(default=None, ge=0, le=60)
    default_task_duration: int | None = Field(default=None, ge=1, le=480)
    max_focus_hours_per_day: int | None = Field(default=None, ge=1, le=16)
    available_days: list[int] | None = None
    auto_schedule_breaks: bool | None = None
    timezone: str | None = None

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, v: str | None) -> str | None:
        if v is None:
            return None
        import zoneinfo
        try:
            zoneinfo.ZoneInfo(v)
        except Exception:
            raise ValueError(f"Invalid IANA timezone identifier: '{v}'")
        return v

    @field_validator("available_days")
    @classmethod
    def validate_days(cls, v: list[int] | None) -> list[int] | None:
        if v is None:
            return None
        for day in v:
            if not isinstance(day, int) or day < 1 or day > 7:
                raise ValueError(f"available_days must contain integers 1 (Monday) to 7 (Sunday), received: {day}")
        return sorted(list(set(v)))


# -----------------------------------------------------------------------------
# Endpoints
# -----------------------------------------------------------------------------
@router.post(
    "/signup",
    response_model=AuthTokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="User Registration",
    description="Registers a new account using Supabase Auth. Does not store passwords directly.",
)
async def signup(
    request: SignUpRequest,
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(
        rate_limit(max_requests=10, window_seconds=60, key_prefix="signup")
    ),
) -> AuthTokenResponse:
    """Register a new user and provision default profile."""
    result = await auth_service.sign_up(
        email=str(request.email),
        password=request.password,
        full_name=request.full_name,
    )

    # Ensure profile and default preferences are initialized
    from sqlalchemy import select

    from app.db.models.profile import Profile, UserPreferences

    query = select(Profile).where(Profile.id == result.user_id)
    existing = await db.scalar(query)
    if not existing:
        profile = Profile(
            id=result.user_id,
            email=str(request.email),
            full_name=request.full_name,
            timezone="UTC",
        )
        db.add(profile)
        preferences = UserPreferences(
            user_id=result.user_id,
            work_start_time="09:00:00",
            work_end_time="18:00:00",
            buffer_minutes=15,
            default_task_duration=45,
            max_focus_hours_per_day=8,
            available_days=[1, 2, 3, 4, 5],
            auto_schedule_breaks=True,
        )
        db.add(preferences)
        await db.commit()

    return result


@router.post(
    "/login",
    response_model=AuthTokenResponse,
    status_code=status.HTTP_200_OK,
    summary="User Login",
    description="Authenticates user credentials against Supabase Auth.",
)
async def login(
    request: LoginRequest,
    _rate_limit: None = Depends(rate_limit(max_requests=15, window_seconds=60, key_prefix="login")),
) -> AuthTokenResponse:
    """Authenticate and obtain JWT access token."""
    return await auth_service.sign_in(
        email=str(request.email),
        password=request.password,
    )


@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    summary="User Logout",
    description="Invalidates current session token.",
)
async def logout(
    current_user: AuthenticatedUser = Depends(get_current_user),
    authorization: str | None = Header(default=None),
) -> dict[str, str]:
    """Log out user and invalidate session."""
    token = authorization.replace("Bearer ", "").strip() if authorization else ""
    await auth_service.sign_out(access_token=token)
    return {"message": "Successfully logged out."}


@router.get(
    "/me",
    response_model=UserProfileResponse,
    status_code=status.HTTP_200_OK,
    summary="Current User Profile",
    description="Returns profile and scheduling preferences for the authenticated identity.",
)
async def get_me(
    profile: Profile = Depends(get_current_active_profile),
    db: AsyncSession = Depends(get_db),
) -> UserProfileResponse:
    """Fetch current user profile and preferences."""
    from sqlalchemy import select

    from app.db.models.profile import UserPreferences

    pref_query = select(UserPreferences).where(UserPreferences.user_id == profile.id)
    pref = await db.scalar(pref_query)

    if not pref:
        pref = UserPreferences(
            user_id=profile.id,
            work_start_time="09:00:00",
            work_end_time="18:00:00",
            buffer_minutes=15,
            default_task_duration=45,
            max_focus_hours_per_day=8,
            available_days=[1, 2, 3, 4, 5],
            auto_schedule_breaks=True,
        )
        db.add(pref)
        await db.commit()

    pref_response = PreferencesResponse(
        work_start_time=pref.work_start_time,
        work_end_time=pref.work_end_time,
        buffer_minutes=pref.buffer_minutes,
        default_task_duration=pref.default_task_duration,
        max_focus_hours_per_day=pref.max_focus_hours_per_day,
        available_days=pref.available_days,
        auto_schedule_breaks=pref.auto_schedule_breaks,
        timezone=profile.timezone,
    )

    return UserProfileResponse(
        id=profile.id,
        email=profile.email,
        full_name=profile.full_name,
        timezone=profile.timezone,
        preferences=pref_response,
    )


@router.get(
    "/preferences",
    response_model=PreferencesResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Preferences",
    description="Retrieve user scheduling preferences (working hours, buffers, timezone).",
)
async def get_preferences(
    profile: Profile = Depends(get_current_active_profile),
    db: AsyncSession = Depends(get_db),
) -> PreferencesResponse:
    """Fetch current scheduling preferences for authenticated user."""
    from sqlalchemy import select

    from app.db.models.profile import UserPreferences

    query = select(UserPreferences).where(UserPreferences.user_id == profile.id)
    pref = await db.scalar(query)

    if not pref:
        pref = UserPreferences(
            user_id=profile.id,
            work_start_time="09:00:00",
            work_end_time="18:00:00",
            buffer_minutes=15,
            default_task_duration=45,
            max_focus_hours_per_day=8,
            available_days=[1, 2, 3, 4, 5],
            auto_schedule_breaks=True,
        )
        db.add(pref)
        await db.commit()
        await db.refresh(pref)

    return PreferencesResponse(
        work_start_time=pref.work_start_time,
        work_end_time=pref.work_end_time,
        buffer_minutes=pref.buffer_minutes,
        default_task_duration=pref.default_task_duration,
        max_focus_hours_per_day=pref.max_focus_hours_per_day,
        available_days=pref.available_days,
        auto_schedule_breaks=pref.auto_schedule_breaks,
        timezone=profile.timezone,
    )


@router.put(
    "/preferences",
    response_model=PreferencesResponse,
    status_code=status.HTTP_200_OK,
    summary="Update Preferences",
    description="Updates user scheduling preferences (working hours, buffers, timezone).",
)
async def update_preferences(
    request: PreferencesUpdateRequest,
    profile: Profile = Depends(get_current_active_profile),
    db: AsyncSession = Depends(get_db),
) -> PreferencesResponse:
    """Update scheduling preferences for authenticated user."""
    from datetime import UTC, datetime
    import uuid
    from sqlalchemy import select

    from app.core.errors import AppException
    from app.db.models.action import AuditLog
    from app.db.models.profile import UserPreferences

    query = select(UserPreferences).where(UserPreferences.user_id == profile.id)
    pref = await db.scalar(query)

    if not pref:
        pref = UserPreferences(user_id=profile.id)
        db.add(pref)

    # Validate working hours range
    start_str = request.work_start_time or pref.work_start_time
    end_str = request.work_end_time or pref.work_end_time
    sh, sm = map(int, start_str.split(":")[:2])
    eh, em = map(int, end_str.split(":")[:2])
    if (sh, sm) == (eh, em):
        raise AppException(
            detail="work_start_time and work_end_time cannot be identical",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="INVALID_WORKING_HOURS",
        )

    updated_fields: list[str] = []
    if request.work_start_time is not None:
        pref.work_start_time = request.work_start_time
        updated_fields.append("work_start_time")
    if request.work_end_time is not None:
        pref.work_end_time = request.work_end_time
        updated_fields.append("work_end_time")
    if request.buffer_minutes is not None:
        pref.buffer_minutes = request.buffer_minutes
        updated_fields.append("buffer_minutes")
    if request.default_task_duration is not None:
        pref.default_task_duration = request.default_task_duration
        updated_fields.append("default_task_duration")
    if request.max_focus_hours_per_day is not None:
        pref.max_focus_hours_per_day = request.max_focus_hours_per_day
        updated_fields.append("max_focus_hours_per_day")
    if request.available_days is not None:
        pref.available_days = request.available_days
        updated_fields.append("available_days")
    if request.auto_schedule_breaks is not None:
        pref.auto_schedule_breaks = request.auto_schedule_breaks
        updated_fields.append("auto_schedule_breaks")
    if request.timezone is not None:
        profile.timezone = request.timezone
        updated_fields.append("timezone")

    audit = AuditLog(
        id=uuid.uuid4(),
        user_id=profile.id,
        action="preferences_updated",
        resource_type="user_preferences",
        resource_id=str(pref.id),
        details={"updated_fields": updated_fields},
        created_at=datetime.now(UTC),
    )
    db.add(audit)

    await db.commit()
    await db.refresh(pref)
    await db.refresh(profile)

    return PreferencesResponse(
        work_start_time=pref.work_start_time,
        work_end_time=pref.work_end_time,
        buffer_minutes=pref.buffer_minutes,
        default_task_duration=pref.default_task_duration,
        max_focus_hours_per_day=pref.max_focus_hours_per_day,
        available_days=pref.available_days,
        auto_schedule_breaks=pref.auto_schedule_breaks,
        timezone=profile.timezone,
    )
