from fastapi import APIRouter

from api.services.audit import get_audit_logs
from api.services.settings import AUDIT_LOG_LIMIT

router = APIRouter()


@router.get("/audit-logs")
def get_logs(limit: int = AUDIT_LOG_LIMIT):
    return get_audit_logs(limit)
