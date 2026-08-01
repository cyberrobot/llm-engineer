import logging
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Request, Security
from fastapi.security import APIKeyCookie

from admin_auth.api_errors import admin_auth_error
from admin_auth.api_models import AdminAuthErrorCode
from admin_auth.domain import Administrator, AdministratorRole, normalize_administrator_email
from admin_auth.passwords import AdministratorPasswordService
from admin_auth.repository import (
    AdministratorAuthRepository,
    PostgresAdministratorAuthRepository,
)
from admin_auth.service import (
    AdministratorAuthenticationService,
    AuthenticationRequired,
    PermissionDenied,
)
from admin_auth.throttling import LoginThrottle
from core.config import (
    DISABLE_RATE_LIMITS,
    REDIS_URL,
    get_admin_authentication_settings,
)
from core.metrics import administrator_authentication_metrics

logger = logging.getLogger(__name__)


@lru_cache
def get_administrator_auth_repository() -> AdministratorAuthRepository:
    return PostgresAdministratorAuthRepository()


@lru_cache
def get_administrator_password_service() -> AdministratorPasswordService:
    return AdministratorPasswordService()


def get_administrator_auth_service(
    repository: Annotated[AdministratorAuthRepository, Depends(get_administrator_auth_repository)],
    passwords: Annotated[AdministratorPasswordService, Depends(get_administrator_password_service)],
) -> AdministratorAuthenticationService:
    settings = get_admin_authentication_settings()
    return AdministratorAuthenticationService(
        repository,
        passwords,
        session_ttl_seconds=settings.session_ttl_seconds,
        login_max_failures=settings.login_max_failures,
        login_lockout_seconds=settings.login_lockout_seconds,
    )


@lru_cache
def get_login_throttle() -> LoginThrottle:
    settings = get_admin_authentication_settings()
    return LoginThrottle(
        REDIS_URL,
        window_seconds=settings.throttle_window_seconds,
        ip_attempts=settings.throttle_ip_attempts,
        email_attempts=settings.throttle_email_attempts,
        global_attempts=settings.throttle_global_attempts,
        enabled=not DISABLE_RATE_LIMITS,
    )


def require_trusted_admin_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    settings = get_admin_authentication_settings()
    if origin is None or origin not in settings.trusted_origins:
        logger.warning("admin_origin_rejected", extra={"reason": "untrusted_origin"})
        raise admin_auth_error(AdminAuthErrorCode.forbidden)


def enforce_login_throttle(
    request: Request,
    email: str,
    throttle: LoginThrottle,
) -> None:
    source_ip = request.client.host if request.client is not None else "unknown"
    decision = throttle.check(source_ip, normalize_administrator_email(email))
    if not decision.allowed:
        administrator_authentication_metrics.login_throttled.inc()
        logger.warning("admin_login_throttled", extra={"source_ip": source_ip})
        raise admin_auth_error(
            AdminAuthErrorCode.too_many_login_attempts,
            retry_after_seconds=decision.retry_after_seconds,
        )


admin_session_cookie = APIKeyCookie(
    name=get_admin_authentication_settings().cookie_name,
    scheme_name="AdministratorSessionCookie",
    description="Opaque HTTP-only administrator session cookie.",
    auto_error=False,
)


def get_session_cookie(
    raw_token: Annotated[str | None, Security(admin_session_cookie)],
) -> str | None:
    return raw_token


def require_authenticated_administrator(
    raw_token: Annotated[str | None, Security(get_session_cookie)],
    service: Annotated[AdministratorAuthenticationService, Depends(get_administrator_auth_service)],
) -> Administrator:
    try:
        _session, administrator = service.authenticate(raw_token)
        return administrator
    except AuthenticationRequired as exc:
        raise admin_auth_error(AdminAuthErrorCode.authentication_required) from exc


def require_administrator_role(
    administrator: Annotated[Administrator, Depends(require_authenticated_administrator)],
    service: Annotated[AdministratorAuthenticationService, Depends(get_administrator_auth_service)],
) -> Administrator:
    try:
        return service.require_role(administrator, AdministratorRole.administrator)
    except PermissionDenied as exc:
        raise admin_auth_error(AdminAuthErrorCode.forbidden) from exc
