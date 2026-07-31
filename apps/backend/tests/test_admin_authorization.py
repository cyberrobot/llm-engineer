import pytest

from core.authentication import ApiPrincipal
from operations.api.errors import administrative_error
from operations.api.models import AdministrativeErrorCode
from operations.application.authorization import (
    AdminAccessLevel,
    AdminAuthenticationRequired,
    AdminPermissionDenied,
    OperationsPermission,
    authorize_operations_access,
)


def principal(*permissions: OperationsPermission) -> ApiPrincipal:
    return ApiPrincipal(
        identifier="test-principal",
        permissions=frozenset(permission.value for permission in permissions),
    )


def test_authorized_administrator_is_allowed_read_and_execute_access():
    administrator = principal(OperationsPermission.read, OperationsPermission.execute)

    assert authorize_operations_access(administrator, AdminAccessLevel.read) is administrator
    assert authorize_operations_access(administrator, AdminAccessLevel.execute) is administrator


def test_read_only_principal_is_allowed_to_read_but_cannot_execute():
    read_only = principal(OperationsPermission.read)

    assert authorize_operations_access(read_only, AdminAccessLevel.read) is read_only
    with pytest.raises(AdminPermissionDenied):
        authorize_operations_access(read_only, AdminAccessLevel.execute)


def test_authenticated_non_administrator_is_forbidden():
    authenticated = ApiPrincipal(
        identifier="ingestion-api-key",
        permissions=frozenset({"ingestion:execute"}),
    )

    with pytest.raises(AdminPermissionDenied):
        authorize_operations_access(authenticated, AdminAccessLevel.read)


@pytest.mark.parametrize("context", [None, object()])
def test_missing_or_malformed_principal_fails_closed(context):
    with pytest.raises(AdminAuthenticationRequired):
        authorize_operations_access(context, AdminAccessLevel.read)


@pytest.mark.parametrize(
    ("code", "status_code"),
    [
        (AdministrativeErrorCode.authentication_required, 401),
        (AdministrativeErrorCode.permission_denied, 403),
        (AdministrativeErrorCode.invalid_request, 400),
        (AdministrativeErrorCode.operation_not_supported, 400),
        (AdministrativeErrorCode.operation_conflict, 409),
        (AdministrativeErrorCode.dependency_unavailable, 503),
    ],
)
def test_administrative_errors_have_safe_machine_readable_contracts(code, status_code):
    error = administrative_error(code)

    assert error.status_code == status_code
    assert error.detail["code"] == code.value
    assert error.detail["message"]
    assert "secret" not in error.detail["message"].lower()
