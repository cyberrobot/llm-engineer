from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256

from config import settings
from fastapi import HTTPException, Request
from infrastructure import auth_audit_connection

PERMITTED_ROLES = ("doctor", "nurse", "analyst", "manager", "agent")


def _auth_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code,
        detail={"code": code, "message": message},
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )


def _authentication_required() -> HTTPException:
    return _auth_error(
        401,
        "authentication_required",
        "Administrator authentication is required.",
    )


def _forbidden() -> HTTPException:
    return _auth_error(
        403,
        "forbidden",
        "The authenticated administrator is not permitted to perform this action.",
    )


@dataclass(frozen=True)
class Authorization:
    principal_id: str
    permitted_roles: tuple[str, ...] = PERMITTED_ROLES


def require_admin(request: Request) -> Authorization:
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise _authentication_required()
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
        if row is not None:
            raise _forbidden()
        raise _authentication_required()
    return Authorization(principal_id=str(row[0]))


def effective_role(requested: str | None, auth: Authorization) -> str:
    role = requested or "doctor"
    if role not in auth.permitted_roles:
        raise _forbidden()
    return role
