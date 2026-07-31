import logging
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, Security
from fastapi.security import APIKeyHeader

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

admin_api_key_header = APIKeyHeader(
    name="X-API-Key",
    scheme_name="AdminApiKey",
    description="Administrative API key required for operations administration.",
    auto_error=False,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def get_authenticated_principal(
    presented_api_key: Annotated[str | None, Security(admin_api_key_header)],
) -> ApiPrincipal:
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

    principal = authenticate_api_key(presented_api_key, tuple(credentials))
    if principal is None:
        logger.warning(
            "admin_authorization_rejected",
            extra={"reason": "authentication_required"},
        )
        raise administrative_error(AdministrativeErrorCode.authentication_required)
    return principal


def require_operations_read(
    principal: Annotated[ApiPrincipal, Depends(get_authenticated_principal)],
) -> ApiPrincipal:
    return _require_access(principal, AdminAccessLevel.read)


def require_operations_execute(
    principal: Annotated[ApiPrincipal, Depends(get_authenticated_principal)],
) -> ApiPrincipal:
    return _require_access(principal, AdminAccessLevel.execute)


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
