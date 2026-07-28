from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from infrastructure.ai.exceptions import (
    AIAuthenticationError,
    AIConfigurationError,
    AIProviderError,
    AIRateLimitError,
    AITimeoutError,
    AIUnavailableError,
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
            headers={"Retry-After": "60"},
        )
    raise exc


def ai_provider_error_handler(request: Request, exc: Exception) -> Response:
    del request
    if not isinstance(exc, AIProviderError):
        raise exc

    status_code = 502
    headers = None
    if isinstance(exc, AIRateLimitError):
        status_code = 429
        headers = {"Retry-After": "30"}
    elif isinstance(exc, AITimeoutError):
        status_code = 504
    elif isinstance(exc, (AIConfigurationError, AIUnavailableError)):
        status_code = 503
    elif isinstance(exc, AIAuthenticationError):
        status_code = 502

    return JSONResponse(
        status_code=status_code,
        content={"detail": str(exc)},
        headers=headers,
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(RateLimitExceeded, rate_limit_handler)
    app.add_exception_handler(AIProviderError, ai_provider_error_handler)
