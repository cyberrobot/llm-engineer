from fastapi import APIRouter

from api.services.audit import get_audit_logs

router = APIRouter()


@router.get("/audit-logs")
def get_logs():
    return get_audit_logs()
