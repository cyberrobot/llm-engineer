import asyncio
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager, suppress
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from application import RequestTimedOut, commit_rag_chat_outcome, prepare_rag_chat
from config import settings
from contracts import RagChatRequest, RagChatResponse
from infrastructure import (
    AuditRepository,
    Cache,
    MaintenanceRepository,
    MaintenanceStateUnavailable,
    PostgresKnowledgeRepository,
    Provider,
    auth_audit_connection,
    knowledge_connection,
)
from logging_config import initialize_logging, request_id_context
from security import effective_role, require_admin

logger = initialize_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.validate()
    app.state.repository = PostgresKnowledgeRepository()
    app.state.audit = AuditRepository()
    app.state.cache = Cache()
    app.state.maintenance = MaintenanceRepository()
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
    started = time.perf_counter()
    raw_request_id = request.headers.get("X-Request-ID")
    try:
        request_id = str(UUID(raw_request_id)) if raw_request_id else str(uuid4())
    except (ValueError, AttributeError):
        request_id = str(uuid4())
    request.state.request_id = request_id
    request_id_context.set(request_id)

    def record_response(status_code: int) -> None:
        logger.info(
            "http_request_completed",
            extra={
                "path": request.url.path
                if request.url.path
                in {"/rag-chat", "/audit-logs", "/health/live", "/health/ready"}
                else "other",
                "status_code": status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 3),
            },
        )

    def early_response(
        status_code: int, content: str, *, retry_after: str | None = None
    ):
        headers = {"X-Request-ID": request_id}
        if request.url.path in {"/rag-chat", "/audit-logs"}:
            headers["Cache-Control"] = "no-store"
        if retry_after is not None:
            headers["Retry-After"] = retry_after
        origin = request.headers.get("origin")
        if origin and origin in settings.allowed_origins:
            headers["Access-Control-Allow-Origin"] = origin
            headers["Access-Control-Allow-Credentials"] = "true"
        record_response(status_code)
        return Response(
            status_code=status_code,
            content=content,
            media_type="application/json",
            headers=headers,
        )

    if request.url.path == "/rag-chat" and request.method != "OPTIONS":
        try:
            maintenance_deadline = time.monotonic() + settings.health_timeout_seconds
            maintenance_enabled = await asyncio.to_thread(
                request.app.state.maintenance.is_enabled, maintenance_deadline
            )
        except MaintenanceStateUnavailable:
            return early_response(
                503,
                '{"detail":{"code":"maintenance_state_unavailable","message":"Service availability cannot currently be determined."}}',
            )
        if maintenance_enabled:
            return early_response(
                503,
                '{"detail":{"code":"maintenance_mode","message":"The service is undergoing maintenance."}}',
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
            logger.warning(
                "rate_limit_rejected",
                extra={"path": request.url.path, "failure_category": "rate_limit"},
            )
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
    record_response(response.status_code)
    return response


@app.get("/health/live")
def live():
    return {"status": "ok"}


@app.get("/health/ready")
def ready():
    try:
        try:
            settings.validate_runtime()
        except Exception:
            logger.error(
                "readiness_check_failed",
                extra={
                    "dependency": "configuration",
                    "failure_category": "configuration_invalid",
                },
            )
            raise
        deadline = time.monotonic() + settings.health_timeout_seconds
        try:
            with knowledge_connection(deadline) as conn:
                conn.execute(
                    """SELECT d.id, c.id, c.text_search, c.embedding
                    FROM public.documents d JOIN public.chunks c ON c.doc_id=d.id
                    LIMIT 0"""
                )
        except Exception:
            logger.error(
                "readiness_check_failed",
                extra={
                    "dependency": "knowledge_database",
                    "failure_category": "dependency_unavailable",
                },
            )
            raise
        try:
            with auth_audit_connection(deadline) as conn:
                conn.execute(
                    """SELECT a.id, a.role, a.status, s.token_hash, s.revoked_at, s.expires_at
                    FROM public.administrators a
                    JOIN public.administrator_sessions s ON s.administrator_id=a.id
                    LIMIT 0"""
                )
                conn.execute(
                    """SELECT maintenance_enabled FROM public.operations_runtime_state
                    WHERE singleton=TRUE LIMIT 0"""
                )
                if not settings.disable_audit:
                    conn.execute(
                        """SELECT id,timestamp,user_role,question,queries,reply,
                        retrieved_chunks,reranked_chunks,evaluation,metrics
                        FROM rag.audit_logs LIMIT 0"""
                    )
        except Exception:
            logger.error(
                "readiness_check_failed",
                extra={
                    "dependency": "auth_audit_database",
                    "failure_category": "dependency_unavailable",
                },
            )
            raise
        if not settings.disable_cache:
            try:
                if not app.state.cache.ping(deadline):
                    raise RuntimeError
            except Exception:
                logger.error(
                    "readiness_check_failed",
                    extra={
                        "dependency": "redis",
                        "failure_category": "dependency_unavailable",
                    },
                )
                raise
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
        deadline = time.monotonic() + settings.request_timeout_seconds
        outcome = await asyncio.wait_for(
            asyncio.to_thread(
                prepare_rag_chat,
                body.message,
                role,
                request.app.state.repository,
                provider,
                request.app.state.cache,
                request.app.state.audit,
                deadline,
            ),
            settings.request_timeout_seconds,
        )
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RequestTimedOut
        commit = asyncio.create_task(
            asyncio.to_thread(
                commit_rag_chat_outcome,
                outcome,
                body.message,
                role,
                request.app.state.cache,
                request.app.state.audit,
                deadline,
            )
        )
        try:
            return await asyncio.wait_for(asyncio.shield(commit), remaining)
        except asyncio.TimeoutError:
            # The adapters use the same absolute deadline for their underlying I/O.
            # Wait for that bounded operation to stop before returning 504 so no
            # worker can mutate state after the response has been sent.
            with suppress(Exception):
                await commit
            raise
    except (asyncio.TimeoutError, RequestTimedOut) as exc:
        logger.warning("rag_chat_timed_out")
        raise HTTPException(
            504, detail="Request timed out", headers={"Cache-Control": "no-store"}
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("rag_chat_failed", extra={"error_type": type(exc).__name__})
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
        logger.error("audit_log_read_failed", extra={"error_type": type(exc).__name__})
        raise HTTPException(
            500, detail="Internal server error", headers={"Cache-Control": "no-store"}
        ) from exc
