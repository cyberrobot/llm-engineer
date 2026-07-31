from datetime import datetime, timezone
from enum import Enum
from typing import Annotated

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, field_validator


class HealthStatus(str, Enum):
    healthy = "healthy"
    degraded = "degraded"
    unhealthy = "unhealthy"
    unknown = "unknown"


class HealthErrorCode(str, Enum):
    dependency_timeout = "dependency_timeout"
    dependency_unavailable = "dependency_unavailable"
    dependency_authentication_failed = "dependency_authentication_failed"
    dependency_misconfigured = "dependency_misconfigured"
    dependency_check_failed = "dependency_check_failed"


class DependencyHealthResult(BaseModel):
    """Safe, serializable result for one non-mutating dependency check."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: Annotated[str, StringConstraints(min_length=1, max_length=64, pattern=r"^[a-z0-9_-]+$")]
    status: HealthStatus
    required: bool
    latency_ms: int = Field(ge=0)
    code: HealthErrorCode | None = None
    checked_at: AwareDatetime

    @field_validator("checked_at")
    @classmethod
    def normalize_checked_at_to_utc(cls, value: datetime) -> datetime:
        return value.astimezone(timezone.utc)

    @classmethod
    def create(
        cls,
        *,
        name: str,
        status: HealthStatus,
        required: bool,
        latency_ms: int,
        code: HealthErrorCode | None = None,
        checked_at: datetime | None = None,
    ) -> "DependencyHealthResult":
        return cls(
            name=name,
            status=status,
            required=required,
            latency_ms=latency_ms,
            code=code,
            checked_at=checked_at or datetime.now(timezone.utc),
        )


class HealthDiagnostic(BaseModel):
    """Aggregate health plus readiness derived only from registered checks."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: HealthStatus
    ready: bool
    generated_at: AwareDatetime
    checks: tuple[DependencyHealthResult, ...]

    @field_validator("generated_at")
    @classmethod
    def normalize_generated_at_to_utc(cls, value: datetime) -> datetime:
        return value.astimezone(timezone.utc)
