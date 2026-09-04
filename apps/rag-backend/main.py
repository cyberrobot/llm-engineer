import asyncio
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

from application import RequestTimedOut, rag_chat
from config import settings
from contracts import RagChatRequest, RagChatResponse
from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from infrastructure import (
    AuditRepository,
    Cache,
    PostgresKnowledgeRepository,
    Provider,
    auth_audit_connection,
    knowledge_connection,
)
from security import effective_role, require_admin


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.validate()
    app.state.repository = PostgresKnowledgeRepository()
    app.state.audit = AuditRepository()
    app.state.cache = Cache()
    app.state.provider = None
    try:
        yield
    finally:
        app.state.cache.close()
        if app.state.provider is not None:
            app.state.provider.close()


app = FastAPI(title="RAG Backend", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.allowed_origins),
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)
rate_windows: dict[tuple[str, str], deque[float]] = defaultdict(deque)


@app.middleware("http")
async def correlation(request: Request, call_next):
    raw_request_id = request.headers.get("X-Request-ID")
    try:
        request_id = str(UUID(raw_request_id)) if raw_request_id else str(uuid4())
    except (ValueError, AttributeError):
        request_id = str(uuid4())
    request.state.request_id = request_id

    def early_response(
        status_code: int, content: str, *, retry_after: str | None = None
    ):
        headers = {"X-Request-ID": request_id}
        if request.url.path in {"/rag-chat", "/audit-logs"}:
            headers["Cache-Control"] = "no-store"
        if retry_after is not None:
            headers["Retry-After"] = retry_after
        return Response(
            status_code=status_code,
            content=content,
            media_type="application/json",
            headers=headers,
        )

    if request.url.path == "/rag-chat" and request.method in {"POST", "PUT", "PATCH"}:
        declared_size = request.headers.get("content-length")
        if declared_size is not None:
            try:
                parsed_size = int(declared_size)
            except ValueError:
                return early_response(400, '{"detail":"Invalid request body size."}')
            if parsed_size < 0 or parsed_size > settings.max_request_bytes:
                return early_response(413, '{"detail":"Request body too large."}')
        raw_body = await request.body()
        if len(raw_body) > settings.max_request_bytes:
            return early_response(413, '{"detail":"Request body too large."}')
    if request.url.path in {"/rag-chat", "/audit-logs"}:
        key = (request.url.path, request.client.host if request.client else "unknown")
        limit = 20 if request.url.path == "/rag-chat" else 60
        now = time.monotonic()
        window = rate_windows[key]
        while window and window[0] <= now - 60:
            window.popleft()
        if len(window) >= limit:
            return early_response(
                429,
                '{"error":{"code":"RATE_LIMIT_EXCEEDED","message":"Too many requests. Please wait a moment before trying again.","retry_after_seconds":60}}',
                retry_after="60",
            )
        window.append(now)
    response = await call_next(request)
    if request.url.path in {"/rag-chat", "/audit-logs"}:
        response.headers["Cache-Control"] = "no-store"
    response.headers["X-Request-ID"] = request_id
    return response


@app.get("/health/live")
def live():
    return {"status": "ok"}


@app.get("/health/ready")
def ready():
    try:
        settings.validate_runtime()
        with knowledge_connection() as conn:
            conn.execute("SELECT 1")
        with auth_audit_connection() as conn:
            conn.execute("SELECT 1")
        if not settings.disable_cache and not app.state.cache.ping():
            raise RuntimeError("Redis unavailable")
        return {"status": "ok"}
    except Exception as exc:
        raise HTTPException(503, detail="Service unavailable") from exc


@app.post("/rag-chat", response_model=RagChatResponse)
async def chat(request: Request, response: Response, body: RagChatRequest):
    auth = require_admin(request)
    role = effective_role(body.user_role, auth)
    response.headers["Cache-Control"] = "no-store"
    try:
        if request.app.state.provider is None:
            request.app.state.provider = Provider()
        provider = request.app.state.provider
        return await asyncio.wait_for(
            asyncio.to_thread(
                rag_chat,
                body.message,
                role,
                request.app.state.repository,
                provider,
                request.app.state.cache,
                request.app.state.audit,
                time.monotonic() + settings.request_timeout_seconds,
            ),
            settings.request_timeout_seconds,
        )
    except (asyncio.TimeoutError, RequestTimedOut) as exc:
        raise HTTPException(
            504, detail="Request timed out", headers={"Cache-Control": "no-store"}
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            500, detail="Internal server error", headers={"Cache-Control": "no-store"}
        ) from exc


@app.get("/audit-logs")
def audit(request: Request, response: Response, limit: int = Query(10, ge=1, le=200)):
    require_admin(request)
    response.headers["Cache-Control"] = "no-store"
    try:
        return request.app.state.audit.list(limit)
    except Exception as exc:
        raise HTTPException(
            500, detail="Internal server error", headers={"Cache-Control": "no-store"}
        ) from exc
