from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from assistant.application.ingestion_service import IngestionFailedError, IngestionJobNotFound
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


def ingestion_job_not_found_handler(request: Request, exc: Exception) -> Response:
    del request
    if not isinstance(exc, IngestionJobNotFound):
        raise exc
    return JSONResponse(status_code=404, content={"detail": str(exc)})


def ingestion_failed_handler(request: Request, exc: Exception) -> Response:
    del request
    if not isinstance(exc, IngestionFailedError):
        raise exc
    return JSONResponse(status_code=500, content={"detail": str(exc)})


async def request_validation_error_handler(request: Request, exc: Exception) -> Response:
    if not isinstance(exc, RequestValidationError):
        raise exc
    if request.url.path.startswith("/public/assistants/"):
        return JSONResponse(
            status_code=422,
            content={
                "detail": {
                    "code": "validation_error",
                    "message": "The chat request is invalid.",
                }
            },
        )
    if not request.url.path.startswith("/admin/auth/"):
        from fastapi.exception_handlers import request_validation_exception_handler

        return await request_validation_exception_handler(request, exc)
    return JSONResponse(
        status_code=400,
        content={
            "detail": {
                "code": "invalid_request",
                "message": "The authentication request is invalid.",
            }
        },
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, request_validation_error_handler)
    app.add_exception_handler(RateLimitExceeded, rate_limit_handler)
    app.add_exception_handler(AIProviderError, ai_provider_error_handler)
    app.add_exception_handler(IngestionJobNotFound, ingestion_job_not_found_handler)
    app.add_exception_handler(IngestionFailedError, ingestion_failed_handler)
