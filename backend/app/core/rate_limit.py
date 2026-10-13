"""In-memory sliding-window rate limiter for sensitive endpoints.

Protects against brute-force attacks on auth and resource exhaustion on AI endpoints.
"""

import time
from collections import defaultdict
from collections.abc import Callable

from fastapi import Request

from app.core.config import settings
from app.core.errors import RateLimitedException

# Store: { key: [timestamp1, timestamp2, ...] }
_request_records: dict[str, list[float]] = defaultdict(list)


def rate_limit(
    max_requests: int = 20,
    window_seconds: int = 60,
    key_prefix: str = "rl",
) -> Callable[[Request], None]:
    """FastAPI dependency for sliding-window rate limiting per client IP."""

    def dependency(request: Request) -> None:
        # Bypass rate limits during automated test execution
        if settings.ENVIRONMENT == "test":
            return

        client_ip = request.client.host if request.client else "unknown"
        key = f"{key_prefix}:{client_ip}:{request.url.path}"
        now = time.time()
        window_start = now - window_seconds

        # Prune older entries
        records = _request_records[key]
        _request_records[key] = [ts for ts in records if ts > window_start]

        if len(_request_records[key]) >= max_requests:
            oldest_in_window = _request_records[key][0]
            retry_after = max(1, int(oldest_in_window + window_seconds - now))
            raise RateLimitedException(
                detail=f"Rate limit exceeded. Maximum {max_requests} requests per {window_seconds}s.",
                retry_after_seconds=retry_after,
            )

        _request_records[key].append(now)

    return dependency


def reset_rate_limits() -> None:
    """Clear in-memory rate limit records (useful for testing)."""
    _request_records.clear()
