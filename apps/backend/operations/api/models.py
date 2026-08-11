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
    cache_region_not_found = "cache_region_not_found"
    cache_key_not_found = "cache_key_not_found"
    audit_entry_not_found = "audit_entry_not_found"
    operational_job_not_found = "operational_job_not_found"


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


class ActionSuccessResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    success: Literal[True] = True
    request_id: str
    correlation_id: str


class CacheKeyInvalidationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    region: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_-]*$")
    key: str = Field(
        min_length=1,
        max_length=512,
        pattern=r"^[^\x00-\x1f\x7f]+$",
    )


class CacheRegionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    entries: int | None
    estimated_memory_bytes: int | None
    hit_count: int | None
    miss_count: int | None
    hit_ratio: float | None


class CacheRegionsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[CacheRegionResponse]


class MaintenanceUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    message: str | None = Field(default=None, max_length=500)


class MaintenanceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    message: str | None
    updated_at: AwareDatetime
    updated_by: str | None
    request_id: str | None = None
    correlation_id: str | None = None


class AuditEntryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    timestamp: AwareDatetime
    user: str
    action: str
    resource: str
    result: str


class AuditPageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[AuditEntryResponse]
    total: int
    limit: int
    offset: int


class AuditDetailResponse(AuditEntryResponse):
    actor: str
    request_id: str
    correlation_id: str
    duration_ms: int
    metadata: dict[str, object]


class OperationalJobResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    status: str
    created_at: AwareDatetime
    started_at: AwareDatetime | None
    completed_at: AwareDatetime | None
    duration_ms: int | None
    retry_count: int
    last_error: str | None
    execution_node: str | None


class OperationalJobsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[OperationalJobResponse]
    total: int
    limit: int
    offset: int


class SummaryCacheResponse(BaseModel):
    regions: int


class SummaryJobsResponse(BaseModel):
    running: int
    failed: int


class SummaryAuditResponse(BaseModel):
    today: int


class OperationsSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    health: str
    maintenance: bool
    cache: SummaryCacheResponse
    jobs: SummaryJobsResponse
    audit: SummaryAuditResponse
