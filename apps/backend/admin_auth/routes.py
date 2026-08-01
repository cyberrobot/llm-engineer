from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response, status

from admin_auth.api_errors import admin_auth_error
from admin_auth.api_models import (
    AdminAuthErrorCode,
    AdminAuthErrorResponse,
    AuthenticatedAdministratorResponse,
    LoginRequest,
)
from admin_auth.dependencies import (
    enforce_login_throttle,
    get_administrator_auth_service,
    get_login_throttle,
    get_session_cookie,
    require_authenticated_administrator,
    require_trusted_admin_origin,
)
from admin_auth.domain import Administrator
from admin_auth.service import AdministratorAuthenticationService, InvalidCredentials
from admin_auth.throttling import LoginThrottle
from core.config import get_admin_authentication_settings

router = APIRouter(prefix="/admin/auth", tags=["Administrator authentication"])

ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"model": AdminAuthErrorResponse},
    401: {"model": AdminAuthErrorResponse},
    403: {"model": AdminAuthErrorResponse},
    429: {"model": AdminAuthErrorResponse},
}


def _prevent_caching(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


@router.post(
    "/login",
    response_model=AuthenticatedAdministratorResponse,
    responses=ERROR_RESPONSES,
    summary="Authenticate an administrator",
)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    service: Annotated[AdministratorAuthenticationService, Depends(get_administrator_auth_service)],
    throttle: Annotated[LoginThrottle, Depends(get_login_throttle)],
    _origin: Annotated[None, Depends(require_trusted_admin_origin)],
) -> AuthenticatedAdministratorResponse:
    enforce_login_throttle(request, str(payload.email), throttle)
    try:
        result = service.login(str(payload.email), payload.password.get_secret_value())
    except InvalidCredentials as exc:
        raise admin_auth_error(AdminAuthErrorCode.invalid_credentials) from exc
    settings = get_admin_authentication_settings()
    response.set_cookie(
        key=settings.cookie_name,
        value=result.session_token,
        max_age=settings.session_ttl_seconds,
        expires=result.expires_at,
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite=settings.cookie_samesite,
    )
    _prevent_caching(response)
    return AuthenticatedAdministratorResponse.from_domain(result.administrator)


@router.get(
    "/me",
    response_model=AuthenticatedAdministratorResponse,
    responses={401: {"model": AdminAuthErrorResponse}},
    summary="Restore the current administrator session",
)
def current_user(
    response: Response,
    administrator: Annotated[Administrator, Depends(require_authenticated_administrator)],
) -> AuthenticatedAdministratorResponse:
    _prevent_caching(response)
    return AuthenticatedAdministratorResponse.from_domain(administrator)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={403: {"model": AdminAuthErrorResponse}},
    summary="Revoke the current administrator session",
)
def logout(
    response: Response,
    raw_token: Annotated[str | None, Depends(get_session_cookie)],
    service: Annotated[AdministratorAuthenticationService, Depends(get_administrator_auth_service)],
    _origin: Annotated[None, Depends(require_trusted_admin_origin)],
) -> None:
    service.logout(raw_token)
    settings = get_admin_authentication_settings()
    response.delete_cookie(
        key=settings.cookie_name,
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite=settings.cookie_samesite,
    )
    _prevent_caching(response)
