"""Consistent error response conventions and exception handling."""

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("mentor_ai.errors")


class ValidationErrorItem(BaseModel):
    """Detailed validation error item."""

    field: str
    issue: str
    received: Any | None = None


class ErrorResponse(BaseModel):
    """Standardized error envelope returned for all non-2xx responses."""

    status_code: int
    error_code: str
    detail: str
    validation_errors: list[ValidationErrorItem] | None = None
    trace_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class AppException(Exception):
    """Base application exception."""

    def __init__(
        self,
        detail: str,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        error_code: str = "INTERNAL_ERROR",
        validation_errors: list[ValidationErrorItem] | None = None,
    ):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code
        self.error_code = error_code
        self.validation_errors = validation_errors


class EntityNotFoundException(AppException):
    def __init__(self, detail: str = "Resource not found"):
        super().__init__(
            detail=detail, status_code=status.HTTP_404_NOT_FOUND, error_code="NOT_FOUND"
        )


class UnauthorizedException(AppException):
    def __init__(self, detail: str = "Authentication required"):
        super().__init__(
            detail=detail, status_code=status.HTTP_401_UNAUTHORIZED, error_code="UNAUTHORIZED"
        )


class ForbiddenException(AppException):
    def __init__(self, detail: str = "Permission denied"):
        super().__init__(
            detail=detail, status_code=status.HTTP_403_FORBIDDEN, error_code="FORBIDDEN"
        )


class ConflictException(AppException):
    def __init__(self, detail: str = "Conflict detected with existing state"):
        super().__init__(detail=detail, status_code=status.HTTP_409_CONFLICT, error_code="CONFLICT")


class RateLimitedException(AppException):
    def __init__(
        self,
        detail: str = "Rate limit exceeded. Please try again later.",
        retry_after_seconds: int = 60,
    ):
        super().__init__(
            detail=detail,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            error_code="RATE_LIMITED",
        )
        self.retry_after_seconds = retry_after_seconds


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """Handle custom application exceptions."""
    trace_id = getattr(request.state, "trace_id", str(uuid.uuid4()))
    logger.warning(
        "Application exception occurred",
        status_code=exc.status_code,
        error_code=exc.error_code,
        detail=exc.detail,
        path=request.url.path,
        trace_id=trace_id,
    )
    error_content = ErrorResponse(
        status_code=exc.status_code,
        error_code=exc.error_code,
        detail=exc.detail,
        validation_errors=exc.validation_errors,
        trace_id=trace_id,
    ).model_dump()
    headers: dict[str, str] = {}
    if isinstance(exc, RateLimitedException):
        headers["Retry-After"] = str(exc.retry_after_seconds)
    return JSONResponse(status_code=exc.status_code, content=error_content, headers=headers)


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Handle standard Starlette / FastAPI HTTPExceptions."""
    trace_id = getattr(request.state, "trace_id", str(uuid.uuid4()))
    error_code = "HTTP_ERROR"
    if exc.status_code == 404:
        error_code = "NOT_FOUND"
    elif exc.status_code == 401:
        error_code = "UNAUTHORIZED"
    elif exc.status_code == 403:
        error_code = "FORBIDDEN"

    error_content = ErrorResponse(
        status_code=exc.status_code,
        error_code=error_code,
        detail=str(exc.detail),
        trace_id=trace_id,
    ).model_dump()
    return JSONResponse(status_code=exc.status_code, content=error_content)


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Handle Pydantic validation errors with formatted error items."""
    trace_id = getattr(request.state, "trace_id", str(uuid.uuid4()))
    validation_items: list[ValidationErrorItem] = []

    for err in exc.errors():
        field_path = " -> ".join(str(loc) for loc in err.get("loc", []))
        validation_items.append(
            ValidationErrorItem(
                field=field_path,
                issue=err.get("msg", "Invalid value"),
                received=err.get("input"),
            )
        )

    logger.info(
        "Request validation failed",
        path=request.url.path,
        errors_count=len(validation_items),
        trace_id=trace_id,
    )

    error_content = ErrorResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        error_code="VALIDATION_ERROR",
        detail="One or more request parameters failed validation.",
        validation_errors=validation_items,
        trace_id=trace_id,
    ).model_dump()
    return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content=error_content)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected server errors, sanitizing details in production."""
    trace_id = getattr(request.state, "trace_id", str(uuid.uuid4()))
    logger.error(
        "Unhandled server error",
        path=request.url.path,
        error=str(exc),
        trace_id=trace_id,
        exc_info=True,
    )

    detail_message = (
        str(exc)
        if not settings.is_production
        else "An unexpected server error occurred. Please report trace_id to support."
    )

    error_content = ErrorResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        error_code="INTERNAL_SERVER_ERROR",
        detail=detail_message,
        trace_id=trace_id,
    ).model_dump()
    return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=error_content)
