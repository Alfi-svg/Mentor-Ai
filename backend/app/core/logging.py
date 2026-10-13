"""Structured logging foundation for Mentor AI."""

import logging
import sys
from typing import Any, cast

import structlog

from app.core.config import settings


def setup_logging() -> None:
    """Configure structured logging based on environment."""
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if settings.is_production:
        # JSON output in production for cloud log ingestion
        processors = shared_processors + [structlog.processors.JSONRenderer()]
    else:
        # Colored, readable output in development
        processors = shared_processors + [structlog.dev.ConsoleRenderer(colors=True)]

    structlog.configure(
        processors=processors,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Configure root standard logging handler
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )


def get_logger(name: str = "mentor_ai") -> structlog.stdlib.BoundLogger:
    """Return a configured structured logger instance."""
    return cast(structlog.stdlib.BoundLogger, structlog.get_logger(name))
