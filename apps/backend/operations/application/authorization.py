from enum import Enum

from core.authentication import ApiPrincipal


class OperationsPermission(str, Enum):
    read = "operations:read"
    execute = "operations:execute"


class AdminAccessLevel(str, Enum):
    read = "read"
    execute = "execute"


class AdminAuthenticationRequired(PermissionError):
    """Raised when no trusted authenticated principal is available."""


class AdminPermissionDenied(PermissionError):
    """Raised when a principal lacks the required operations permission."""


REQUIRED_PERMISSION = {
    AdminAccessLevel.read: OperationsPermission.read,
    AdminAccessLevel.execute: OperationsPermission.execute,
}


def authorize_operations_access(
    principal: ApiPrincipal | None,
    access_level: AdminAccessLevel,
) -> ApiPrincipal:
    """Fail closed while keeping read and state-changing access distinct."""

    if not isinstance(principal, ApiPrincipal):
        raise AdminAuthenticationRequired
    required_permission = REQUIRED_PERMISSION[access_level].value
    if required_permission not in principal.permissions:
        raise AdminPermissionDenied
    return principal
