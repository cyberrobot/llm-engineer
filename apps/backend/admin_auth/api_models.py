from enum import Enum

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, field_validator

from admin_auth.domain import Administrator, AdministratorRole, normalize_administrator_email
from admin_auth.passwords import MAXIMUM_PASSWORD_LENGTH


class AdminAuthErrorCode(str, Enum):
    invalid_credentials = "invalid_credentials"
    authentication_required = "authentication_required"
    forbidden = "forbidden"
    too_many_login_attempts = "too_many_login_attempts"
    invalid_request = "invalid_request"


class AdminAuthErrorDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: AdminAuthErrorCode
    message: str


class AdminAuthErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    detail: AdminAuthErrorDetail


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr = Field(max_length=254)
    password: SecretStr = Field(min_length=1, max_length=MAXIMUM_PASSWORD_LENGTH)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return normalize_administrator_email(str(value))


class AdministratorUser(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    email: EmailStr
    role: AdministratorRole

    @classmethod
    def from_domain(cls, administrator: Administrator) -> "AdministratorUser":
        return cls(
            id=str(administrator.id),
            email=administrator.email,
            role=administrator.role,
        )


class AuthenticatedAdministratorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user: AdministratorUser

    @classmethod
    def from_domain(cls, administrator: Administrator) -> "AuthenticatedAdministratorResponse":
        return cls(user=AdministratorUser.from_domain(administrator))
