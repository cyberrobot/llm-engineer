from fastapi import HTTPException

from admin_auth.api_models import AdminAuthErrorCode

SAFE_AUTH_ERRORS = {
    AdminAuthErrorCode.invalid_credentials: (401, "The email or password is invalid."),
    AdminAuthErrorCode.authentication_required: (401, "Administrator authentication is required."),
    AdminAuthErrorCode.forbidden: (
        403,
        "The authenticated administrator is not permitted to perform this action.",
    ),
    AdminAuthErrorCode.too_many_login_attempts: (
        429,
        "Too many login attempts. Please try again later.",
    ),
    AdminAuthErrorCode.invalid_request: (400, "The authentication request is invalid."),
}


def admin_auth_error(
    code: AdminAuthErrorCode, *, retry_after_seconds: int | None = None
) -> HTTPException:
    status_code, message = SAFE_AUTH_ERRORS[code]
    headers = {"Cache-Control": "no-store", "Pragma": "no-cache"}
    if retry_after_seconds is not None:
        headers["Retry-After"] = str(retry_after_seconds)
    return HTTPException(
        status_code=status_code,
        detail={"code": code.value, "message": message},
        headers=headers,
    )
