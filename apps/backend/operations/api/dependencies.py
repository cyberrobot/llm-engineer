import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, NoReturn

from fastapi import Depends, HTTPException, Request, Response, Security
from fastapi.security import APIKeyHeader

from admin_auth.dependencies import (
    get_administrator_auth_service,
    get_session_cookie,
    require_trusted_admin_origin,
)
from admin_auth.domain import AdministratorRole
from admin_auth.service import (
    AdministratorAuthenticationService,
    AuthenticationRequired,
    PermissionDenied,
)
from core.authentication import ApiKeyCredential, ApiPrincipal, authenticate_api_key
from core.config import get_admin_api_key, get_ingest_api_key
from operations.api.errors import administrative_error
from operations.api.models import AdministrativeErrorCode
from operations.application.authorization import (
    AdminAccessLevel,
    AdminAuthenticationRequired,
    AdminPermissionDenied,
    OperationsPermission,
    authorize_operations_access,
)

logger = logging.getLogger(__name__)


class OperationsAuthenticationMode(str, Enum):
    api_key = "api_key"
    administrator_session = "administrator_session"


@dataclass(frozen=True, slots=True)
class OperationsCaller:
    principal: ApiPrincipal
    authentication_mode: OperationsAuthenticationMode


ADMINISTRATOR_OPERATIONS_PERMISSIONS = {
    AdministratorRole.administrator: frozenset(
        {
            OperationsPermission.read.value,
            OperationsPermission.execute.value,
        }
    )
}


admin_api_key_header = APIKeyHeader(
    name="X-API-Key",
    scheme_name="AdminApiKey",
    description="Server-side Operations API key for operational clients.",
    auto_error=False,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def prevent_operations_caching(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


def _api_key_credentials() -> tuple[ApiKeyCredential, ...]:
    credentials: list[ApiKeyCredential] = []
    admin_api_key = get_admin_api_key()
    if admin_api_key:
        credentials.append(
            ApiKeyCredential(
                api_key=admin_api_key,
                principal=ApiPrincipal(
                    identifier="admin-api-key",
                    permissions=frozenset(
                        {
                            OperationsPermission.read.value,
                            OperationsPermission.execute.value,
                        }
                    ),
                ),
            )
        )
    ingest_api_key = get_ingest_api_key()
    if ingest_api_key:
        credentials.append(
            ApiKeyCredential(
                api_key=ingest_api_key,
                principal=ApiPrincipal(
                    identifier="ingestion-api-key",
                    permissions=frozenset({"ingestion:execute"}),
                ),
            )
        )
    return tuple(credentials)


def _reject_authentication() -> NoReturn:
    logger.warning(
        "admin_authorization_rejected",
        extra={"reason": "authentication_required"},
    )
    raise administrative_error(AdministrativeErrorCode.authentication_required)


def get_operations_caller(
    presented_api_key: Annotated[str | None, Security(admin_api_key_header)],
    raw_session_token: Annotated[str | None, Security(get_session_cookie)],
    administrator_auth: Annotated[
        AdministratorAuthenticationService, Depends(get_administrator_auth_service)
    ],
) -> OperationsCaller:
    """Resolve one caller with explicit API-key precedence over the browser session."""

    if presented_api_key is not None:
        principal = authenticate_api_key(presented_api_key, _api_key_credentials())
        if principal is None:
            _reject_authentication()
        return OperationsCaller(principal, OperationsAuthenticationMode.api_key)

    try:
        _session, administrator = administrator_auth.authenticate(raw_session_token)
        administrator_auth.require_role(administrator, AdministratorRole.administrator)
    except AuthenticationRequired:
        _reject_authentication()
    except PermissionDenied as exc:
        logger.warning(
            "admin_authorization_rejected",
            extra={"reason": "permission_denied", "administrator_id": str(administrator.id)},
        )
        raise administrative_error(AdministrativeErrorCode.permission_denied) from exc

    principal = ApiPrincipal(
        identifier=str(administrator.id),
        permissions=ADMINISTRATOR_OPERATIONS_PERMISSIONS.get(administrator.role, frozenset()),
    )
    return OperationsCaller(principal, OperationsAuthenticationMode.administrator_session)


def get_authenticated_principal(
    caller: Annotated[OperationsCaller, Depends(get_operations_caller)],
) -> ApiPrincipal:
    return caller.principal


def require_operations_read(
    principal: Annotated[ApiPrincipal, Depends(get_authenticated_principal)],
) -> ApiPrincipal:
    return _require_access(principal, AdminAccessLevel.read)


def require_operations_execute(
    request: Request,
    caller: Annotated[OperationsCaller, Depends(get_operations_caller)],
) -> ApiPrincipal:
    principal = _require_access(caller.principal, AdminAccessLevel.execute)
    if caller.authentication_mode is OperationsAuthenticationMode.administrator_session:
        try:
            require_trusted_admin_origin(request)
        except HTTPException as exc:
            raise administrative_error(AdministrativeErrorCode.permission_denied) from exc
    return principal


def _require_access(principal: ApiPrincipal, access_level: AdminAccessLevel) -> ApiPrincipal:
    try:
        return authorize_operations_access(principal, access_level)
    except AdminAuthenticationRequired as exc:
        logger.warning(
            "admin_authorization_rejected",
            extra={"access_level": access_level.value, "reason": "authentication_required"},
        )
        raise administrative_error(AdministrativeErrorCode.authentication_required) from exc
    except AdminPermissionDenied as exc:
        logger.warning(
            "admin_authorization_rejected",
            extra={
                "access_level": access_level.value,
                "principal_id": principal.identifier,
                "reason": "permission_denied",
            },
        )
        raise administrative_error(AdministrativeErrorCode.permission_denied) from exc
