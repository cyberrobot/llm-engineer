from fastapi import APIRouter, Request

from api.core.rate_limit import limiter
from api.services.audit import get_audit_logs
from api.services.settings import AUDIT_LOG_LIMIT

router = APIRouter()


@router.get("/audit-logs")
@limiter.limit("60/minute")
def get_logs(request: Request, limit: int = AUDIT_LOG_LIMIT):
    return get_audit_logs(limit)
