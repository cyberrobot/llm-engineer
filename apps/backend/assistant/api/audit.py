from fastapi import APIRouter, Request

from assistant.application.audit import get_audit_logs
from core.config import AUDIT_LOG_LIMIT
from shared.dependencies.rate_limit import limiter

router = APIRouter()


@router.get("/audit-logs")
@limiter.limit("60/minute")
def get_logs(request: Request, limit: int = AUDIT_LOG_LIMIT):
    return get_audit_logs(limit)
