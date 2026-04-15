from fastapi import APIRouter

from api.services.audit import AUDIT_LOGS

router = APIRouter()


@router.get("/audit-logs")
def get_audit_logs():
    return AUDIT_LOGS
