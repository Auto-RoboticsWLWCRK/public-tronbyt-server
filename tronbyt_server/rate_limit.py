"""Rate limiting middleware using SlowAPI.

This module provides rate limiting for public endpoints to protect
against abuse in multi-tenant mode.

Usage:
    from tronbyt_server.rate_limit import limiter, rate_limit_exceeded_handler

    # In main.py:
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

    # In routes:
    @router.get("/public-endpoint")
    @limiter.limit("10/minute")
    async def public_endpoint(request: Request):
        ...
"""

import logging
from typing import TYPE_CHECKING, Any, Callable

from fastapi import Request, status
from fastapi.responses import JSONResponse

if TYPE_CHECKING:
    from slowapi import Limiter
    from slowapi.errors import RateLimitExceeded

logger = logging.getLogger(__name__)


def get_rate_limit_key(request: Request) -> str:
    """Get the rate limit key for a request.

    Uses the client's IP address as the rate limit key.
    Falls back to a default key if IP cannot be determined.

    Args:
        request: The FastAPI request object.

    Returns:
        A string key for rate limiting.
    """
    # Try X-Forwarded-For header first (for requests behind proxy)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # Get the first IP in the chain (original client)
        return forwarded_for.split(",")[0].strip()

    # Try X-Real-IP header
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip

    # Fall back to direct client IP
    if request.client:
        return request.client.host

    return "unknown"


def create_limiter() -> "Limiter | None":
    """Create a SlowAPI limiter instance.

    Returns:
        A configured Limiter instance, or None if slowapi is not available.
    """
    try:
        from slowapi import Limiter

        from tronbyt_server.config import get_settings

        settings = get_settings()

        return Limiter(
            key_func=get_rate_limit_key,
            default_limits=[f"{settings.RATE_LIMIT_REQUESTS}/minute"],
        )
    except ImportError:
        logger.warning("slowapi not installed, rate limiting disabled")
        return None


def rate_limit_exceeded_handler(
    request: Request, exc: "RateLimitExceeded"
) -> JSONResponse:
    """Handle rate limit exceeded errors.

    Args:
        request: The FastAPI request object.
        exc: The RateLimitExceeded exception.

    Returns:
        JSONResponse with 429 status code.
    """
    logger.warning(f"Rate limit exceeded for {get_rate_limit_key(request)}")

    # Cast exc to Any to access attributes that may not be statically typed
    exc_any: Any = exc
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={
            "error": "Rate limit exceeded",
            "detail": str(exc_any.detail)
            if hasattr(exc_any, "detail")
            else "Too many requests",
            "retry_after": getattr(exc_any, "retry_after", 60),
        },
    )


# Create the limiter instance (may be None if slowapi not installed)
limiter = create_limiter()


def rate_limit(limit: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator to apply rate limiting to a route.

    This is a wrapper around the slowapi limiter.limit() decorator.
    If slowapi is not installed, it returns a no-op decorator.

    Args:
        limit: Rate limit string (e.g., "10/minute", "100/hour").

    Returns:
        A decorator function.
    """
    if limiter is not None:
        return limiter.limit(limit)

    # No-op decorator if limiter is not available
    def no_op_decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        return func

    return no_op_decorator
