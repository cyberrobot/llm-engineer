from fastapi import HTTPException

from operations.api.models import AdministrativeErrorCode

SAFE_ADMINISTRATIVE_ERRORS = {
    AdministrativeErrorCode.authentication_required: (
        401,
        "Administrative authentication is required.",
    ),
    AdministrativeErrorCode.permission_denied: (
        403,
        "The authenticated principal lacks the required administrative permission.",
    ),
    AdministrativeErrorCode.invalid_request: (400, "The administrative request is invalid."),
    AdministrativeErrorCode.operation_not_supported: (
        400,
        "The requested administrative operation is not supported.",
    ),
    AdministrativeErrorCode.operation_conflict: (
        409,
        "The administrative operation conflicts with current system state.",
    ),
    AdministrativeErrorCode.dependency_unavailable: (
        503,
        "A required dependency is unavailable.",
    ),
}


def administrative_error(code: AdministrativeErrorCode) -> HTTPException:
    """Build a production-safe, machine-readable administrative API error."""

    status_code, message = SAFE_ADMINISTRATIVE_ERRORS[code]
    headers = {"WWW-Authenticate": "ApiKey"} if status_code == 401 else None
    return HTTPException(
        status_code=status_code,
        detail={"code": code.value, "message": message},
        headers=headers,
    )
