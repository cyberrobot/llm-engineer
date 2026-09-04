from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256

from config import settings
from fastapi import HTTPException, Request
from infrastructure import auth_audit_connection

PERMITTED_ROLES = ("doctor", "nurse", "analyst", "manager", "agent")


@dataclass(frozen=True)
class Authorization:
    principal_id: str
    permitted_roles: tuple[str, ...] = PERMITTED_ROLES


def require_admin(request: Request) -> Authorization:
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise HTTPException(401, detail="Authentication required")
    try:
        with auth_audit_connection() as conn:
            row = conn.execute(
                """SELECT a.id, a.role FROM administrator_sessions s
                JOIN administrators a ON a.id = s.administrator_id
                WHERE s.token_hash = %s AND s.revoked_at IS NULL
                AND s.expires_at > %s AND a.status = 'active'""",
                (sha256(token.encode()).hexdigest(), datetime.now(timezone.utc)),
            ).fetchone()
    except Exception as exc:
        raise HTTPException(503, detail="Service unavailable") from exc
    if row is None or row[1] != "administrator":
        raise HTTPException(401, detail="Authentication required")
    return Authorization(principal_id=str(row[0]))


def effective_role(requested: str | None, auth: Authorization) -> str:
    role = requested or "doctor"
    if role not in auth.permitted_roles:
        raise HTTPException(403, detail="Forbidden")
    return role
