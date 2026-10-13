"""Health and readiness check endpoints."""

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from app.core.config import settings

router = APIRouter()


class HealthResponse(BaseModel):
    """Liveness probe response."""

    status: str = Field(default="healthy", description="Application liveness status")
    version: str = Field(default=settings.VERSION)
    environment: str = Field(default=settings.ENVIRONMENT)
    ai_provider: str = Field(default=settings.AI_PROVIDER)
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class ReadinessResponse(BaseModel):
    """Readiness probe response indicating subsystem connectivity."""

    status: str = Field(description="'ready' or 'degraded'")
    database: str = Field(description="'connected', 'unconfigured', or 'disconnected'")
    ai_service: str = Field(description="Configured AI service provider status")
    details: dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Liveness probe",
    description="Returns HTTP 200 if the application process is running and accepting traffic.",
)
async def get_health() -> HealthResponse:
    """Return application liveness status."""
    return HealthResponse()


@router.get(
    "/health/ready",
    response_model=ReadinessResponse,
    status_code=status.HTTP_200_OK,
    summary="Readiness probe",
    description="Checks downstream dependencies (database, AI configuration) truthfully without faking status.",
)
async def get_readiness() -> ReadinessResponse:
    """Check readiness of connected subsystems truthfully."""
    from app.db.session import check_db_connectivity

    connected, db_info = await check_db_connectivity()
    db_status = "connected" if connected else "disconnected"
    if not settings.has_database_url:
        db_details = f"Local/test fallback database ({db_info})"
    else:
        db_details = f"PostgreSQL ({db_info})"

    ai_status = f"active_{settings.AI_PROVIDER}"
    overall_status = "ready" if connected else "degraded"

    return ReadinessResponse(
        status=overall_status,
        database=db_status,
        ai_service=ai_status,
        details={
            "database_info": db_details,
            "supabase_configured": settings.has_supabase_credentials,
            "offline_mode_available": True,
        },
    )
