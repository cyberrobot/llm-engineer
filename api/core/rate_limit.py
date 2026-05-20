import os

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

DISABLE_RATE_LIMITS = os.getenv("DISABLE_RATE_LIMITS", "false").lower() == "true"

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=None if DISABLE_RATE_LIMITS else os.getenv("REDIS_URL"),
    enabled=not DISABLE_RATE_LIMITS,
)


def rate_limit_handler(request: Request, exc: Exception) -> Response:
    if isinstance(exc, RateLimitExceeded):
        return JSONResponse(
            status_code=429,
            content={
                "error": {
                    "code": "RATE_LIMIT_EXCEEDED",
                    "message": "Too many requests. Please wait a moment before trying again.",
                    "retry_after_seconds": 60,
                }
            },
            headers={
                "Retry-After": "60",
            },
        )
    raise exc
