from contextvars import ContextVar, Token
from uuid import UUID, uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

request_id_context: ContextVar[str | None] = ContextVar("request_id", default=None)


def normalise_request_id(value: str | None) -> str:
    if value is not None:
        try:
            return str(UUID(value))
        except ValueError:
            pass
    return str(uuid4())


def set_request_id(value: str) -> Token[str | None]:
    return request_id_context.set(value)


def reset_request_id(token: Token[str | None]) -> None:
    request_id_context.reset(token)


class RequestCorrelationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = normalise_request_id(request.headers.get("X-Request-ID"))
        token = set_request_id(request_id)
        request.state.request_id = request_id
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            reset_request_id(token)
