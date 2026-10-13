"""Mentor AI — FastAPI Application Entrypoint."""

import time
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any, cast

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.errors import (
    AppException,
    app_exception_handler,
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.core.logging import get_logger, setup_logging

logger = get_logger("mentor_ai.main")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to inject trace_id and log request/response metrics."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        trace_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.trace_id = trace_id
        start_time = time.perf_counter()

        logger.info(
            "HTTP request started",
            method=request.method,
            path=request.url.path,
            trace_id=trace_id,
            client_host=request.client.host if request.client else None,
        )

        try:
            response: Response = await call_next(request)
            process_time_ms = round((time.perf_counter() - start_time) * 1000, 2)
            response.headers["X-Request-ID"] = trace_id
            response.headers["X-Response-Time-Ms"] = str(process_time_ms)
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["X-XSS-Protection"] = "1; mode=block"
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
            if settings.ENVIRONMENT == "production":
                response.headers["Strict-Transport-Security"] = (
                    "max-age=31536000; includeSubDomains"
                )

            logger.info(
                "HTTP request completed",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=process_time_ms,
                trace_id=trace_id,
            )
            return response
        except Exception:
            process_time_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.error(
                "HTTP request failed with unhandled exception",
                method=request.method,
                path=request.url.path,
                duration_ms=process_time_ms,
                trace_id=trace_id,
            )
            raise


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Lifespan event handler for startup and shutdown initialization."""
    setup_logging()
    logger.info(
        "Mentor AI backend starting",
        version=settings.VERSION,
        environment=settings.ENVIRONMENT,
        allowed_origins=settings.ALLOWED_ORIGINS,
    )
    yield
    logger.info("Mentor AI backend shutting down")


def create_app() -> FastAPI:
    """FastAPI application factory."""
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        openapi_url=f"{settings.API_V1_STR}/openapi.json",
        docs_url=f"{settings.API_V1_STR}/docs",
        redoc_url=f"{settings.API_V1_STR}/redoc",
        lifespan=lifespan,
    )

    # 1. Custom Logging & Trace ID Middleware
    app.add_middleware(RequestLoggingMiddleware)

    # 2. Strict Environment-Controlled CORS Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    # 3. Exception Handlers for Structured Error Envelopes
    app.add_exception_handler(AppException, cast(Any, app_exception_handler))
    app.add_exception_handler(StarletteHTTPException, cast(Any, http_exception_handler))
    app.add_exception_handler(RequestValidationError, cast(Any, validation_exception_handler))
    app.add_exception_handler(Exception, cast(Any, unhandled_exception_handler))

    # 4. Include Versioned API Routers
    app.include_router(api_router, prefix=settings.API_V1_STR)

    # 5. Mount Authenticated MCP Server for Remote Agents
    from app.services.mcp.server import create_authenticated_mcp_app

    app.mount("/mcp", create_authenticated_mcp_app())

    # 6. Root status route
    @app.get("/", tags=["root"], summary="Root service status")
    async def root_status() -> dict[str, str]:
        return {
            "name": settings.PROJECT_NAME,
            "version": settings.VERSION,
            "docs_url": f"{settings.API_V1_STR}/docs",
            "health_url": f"{settings.API_V1_STR}/health",
            "mcp_url": "/mcp/sse",
        }

    return app


app = create_app()
