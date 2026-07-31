from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from operations.domain.health import DependencyHealthResult, HealthStatus


class AdministrativeErrorCode(str, Enum):
    authentication_required = "admin_authentication_required"
    permission_denied = "admin_permission_denied"
    invalid_request = "invalid_admin_request"
    operation_not_supported = "operation_not_supported"
    operation_conflict = "operation_conflict"
    dependency_unavailable = "dependency_unavailable"


class AdministrativeErrorDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: AdministrativeErrorCode
    message: str


class AdministrativeErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    detail: AdministrativeErrorDetail


class OperationsResponseMetadata(BaseModel):
    """Small, composable metadata shared by administrative responses."""

    model_config = ConfigDict(extra="forbid")

    generated_at: AwareDatetime
    request_id: str | None = None

    @field_validator("generated_at")
    @classmethod
    def normalize_generated_at_to_utc(cls, value: datetime) -> datetime:
        return value.astimezone(timezone.utc)


class OperationsRootResponse(OperationsResponseMetadata):
    service: Literal["operations"] = "operations"
    status: Literal["available"] = "available"
    capabilities: list[str] = Field(default_factory=list)


class OperationsHealthResponse(OperationsResponseMetadata):
    status: HealthStatus
    checks: list[DependencyHealthResult]
