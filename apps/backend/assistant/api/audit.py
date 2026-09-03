import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from admin_auth.dependencies import require_administrator_role
from admin_auth.domain import Administrator
from assistant.application.audit import get_audit_logs
from core.config import AUDIT_LOG_LIMIT
from shared.dependencies.rate_limit import limiter

router = APIRouter()
logger = logging.getLogger(__name__)
MAX_AUDIT_LOG_LIMIT = 200


@router.get("/audit-logs")
@limiter.limit("60/minute")
def get_logs(
    request: Request,
    response: Response,
    _administrator: Annotated[Administrator, Depends(require_administrator_role)],
    limit: Annotated[int, Query(ge=1, le=MAX_AUDIT_LOG_LIMIT)] = AUDIT_LOG_LIMIT,
):
    del request
    response.headers["Cache-Control"] = "no-store"
    try:
        return get_audit_logs(limit)
    except Exception as exc:
        logger.error(
            "rag_ui_audit_read_failed",
            extra={"error_type": type(exc).__name__},
        )
        raise HTTPException(
            status_code=500,
            detail="Internal server error",
            headers={"Cache-Control": "no-store"},
        ) from exc
