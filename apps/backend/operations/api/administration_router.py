import logging
from collections.abc import Callable
from time import perf_counter
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, Request
from pydantic import AwareDatetime

from core.authentication import ApiPrincipal
from operations.api.administration_dependencies import (
    get_audit_query_service,
    get_cache_administration_service,
    get_job_operations_service,
    get_maintenance_service,
    get_operations_summary_service,
    get_rag_audit_reader,
)
from operations.api.dependencies import require_operations_execute
from operations.api.errors import administrative_error
from operations.api.health_dependencies import get_health_service
from operations.api.models import (
    ActionSuccessResponse,
    AdministrativeErrorCode,
    AdministrativeErrorResponse,
    AuditDetailResponse,
    AuditEntryResponse,
    AuditPageResponse,
    CacheKeyInvalidationRequest,
    CacheRegionResponse,
    CacheRegionsResponse,
    MaintenanceResponse,
    MaintenanceUpdateRequest,
    OperationalJobResponse,
    OperationalJobsResponse,
    OperationsSummaryResponse,
    RagAuditEntryResponse,
    SummaryAssistantsResponse,
    SummaryAuditResponse,
    SummaryCacheResponse,
    SummaryIngestionResponse,
    SummaryJobsResponse,
    SummaryKnowledgeSourcesResponse,
)
from operations.application.administration import (
    AuditQueryService,
    CacheAdministrationService,
    JobOperationsService,
    MaintenanceService,
    OperationsSummaryService,
    elapsed_milliseconds,
)
from operations.application.health import HealthService
from operations.domain.administration import (
    AuditEntry,
    AuditEntryNotFound,
    AuditFilters,
    AuditResult,
    CacheKeyNotFound,
    CacheRegionNotFound,
    HealthOverview,
    OperationalJob,
    OperationalJobNotFound,
    OperationsDependencyUnavailable,
)

logger = logging.getLogger(__name__)
router = APIRouter(
    responses={
        401: {"model": AdministrativeErrorResponse, "description": "Authentication required"},
        403: {"model": AdministrativeErrorResponse, "description": "Permission denied"},
    }
)


def _ids(request: Request) -> tuple[str, str]:
    request_id = getattr(request.state, "request_id", "unknown")
    return request_id, request_id


def _execute(
    action: Callable[[], Any],
    *,
    audit: AuditQueryService,
    actor: str,
    action_name: str,
    resource: str,
    request: Request,
    metadata: dict[str, object] | None = None,
) -> Any:
    started = perf_counter()
    request_id, correlation_id = _ids(request)
    audit_entry = audit.start(
        actor=actor,
        action=action_name,
        resource=resource,
        request_id=request_id,
        correlation_id=correlation_id,
        metadata=metadata,
    )
    try:
        result = action()
    except Exception as exc:
        audit.finish(
            audit_entry,
            result=AuditResult.failure,
            duration_ms=elapsed_milliseconds(started),
            metadata={"failure_type": type(exc).__name__},
        )
        logger.warning(
            "administrative_action_failed",
            extra={"action": action_name, **dict(metadata or {})},
        )
        if isinstance(exc, CacheRegionNotFound):
            raise administrative_error(AdministrativeErrorCode.cache_region_not_found) from exc
        if isinstance(exc, CacheKeyNotFound):
            raise administrative_error(AdministrativeErrorCode.cache_key_not_found) from exc
        if isinstance(exc, OperationsDependencyUnavailable):
            raise exc
        if isinstance(exc, ValueError):
            raise administrative_error(AdministrativeErrorCode.invalid_request) from exc
        raise
    audit.finish(
        audit_entry,
        result=AuditResult.success,
        duration_ms=elapsed_milliseconds(started),
    )
    logger.info(
        "administrative_action_completed",
        extra={"action": action_name, **dict(metadata or {})},
    )
    return result


@router.get(
    "/cache", response_model=CacheRegionsResponse, summary="List cache regions and statistics"
)
def list_cache_regions(
    service: Annotated[CacheAdministrationService, Depends(get_cache_administration_service)],
) -> CacheRegionsResponse:
    return CacheRegionsResponse(
        items=[CacheRegionResponse(**vars(item)) for item in service.list_regions()]
    )


@router.post(
    "/cache/clear",
    response_model=ActionSuccessResponse,
    summary="Clear all registered cache regions",
)
def clear_cache(
    request: Request,
    principal: Annotated[ApiPrincipal, Depends(require_operations_execute)],
    service: Annotated[CacheAdministrationService, Depends(get_cache_administration_service)],
    audit: Annotated[AuditQueryService, Depends(get_audit_query_service)],
) -> ActionSuccessResponse:
    _execute(
        service.clear_all,
        audit=audit,
        actor=principal.identifier,
        action_name="cache.clear",
        resource="cache",
        request=request,
    )
    request_id, correlation_id = _ids(request)
    return ActionSuccessResponse(request_id=request_id, correlation_id=correlation_id)


@router.post(
    "/cache/regions/{region}/clear",
    response_model=ActionSuccessResponse,
    summary="Clear one cache region",
)
def clear_cache_region(
    request: Request,
    region: Annotated[str, Path(pattern=r"^[a-z][a-z0-9_-]{0,63}$")],
    principal: Annotated[ApiPrincipal, Depends(require_operations_execute)],
    service: Annotated[CacheAdministrationService, Depends(get_cache_administration_service)],
    audit: Annotated[AuditQueryService, Depends(get_audit_query_service)],
) -> ActionSuccessResponse:
    _execute(
        lambda: service.clear_region(region),
        audit=audit,
        actor=principal.identifier,
        action_name="cache.region.clear",
        resource=f"cache:{region}",
        request=request,
        metadata={"region": region},
    )
    request_id, correlation_id = _ids(request)
    return ActionSuccessResponse(request_id=request_id, correlation_id=correlation_id)


@router.post("/cache/key", response_model=ActionSuccessResponse, summary="Invalidate one cache key")
def invalidate_cache_key(
    payload: CacheKeyInvalidationRequest,
    request: Request,
    principal: Annotated[ApiPrincipal, Depends(require_operations_execute)],
    service: Annotated[CacheAdministrationService, Depends(get_cache_administration_service)],
    audit: Annotated[AuditQueryService, Depends(get_audit_query_service)],
) -> ActionSuccessResponse:
    _execute(
        lambda: service.invalidate_key(payload.region, payload.key),
        audit=audit,
        actor=principal.identifier,
        action_name="cache.key.invalidate",
        resource=f"cache:{payload.region}",
        request=request,
        metadata={"region": payload.region},
    )
    request_id, correlation_id = _ids(request)
    return ActionSuccessResponse(request_id=request_id, correlation_id=correlation_id)


@router.get("/maintenance", response_model=MaintenanceResponse, summary="Read maintenance mode")
def get_maintenance(
    service: Annotated[MaintenanceService, Depends(get_maintenance_service)],
) -> MaintenanceResponse:
    return MaintenanceResponse(**vars(service.get()))


@router.put("/maintenance", response_model=MaintenanceResponse, summary="Update maintenance mode")
def update_maintenance(
    payload: MaintenanceUpdateRequest,
    request: Request,
    principal: Annotated[ApiPrincipal, Depends(require_operations_execute)],
    service: Annotated[MaintenanceService, Depends(get_maintenance_service)],
    audit: Annotated[AuditQueryService, Depends(get_audit_query_service)],
) -> MaintenanceResponse:
    state = _execute(
        lambda: service.update(
            enabled=payload.enabled, message=payload.message, actor=principal.identifier
        ),
        audit=audit,
        actor=principal.identifier,
        action_name="maintenance.update",
        resource="maintenance",
        request=request,
        metadata={"enabled": payload.enabled},
    )
    request_id, correlation_id = _ids(request)
    return MaintenanceResponse(**vars(state), request_id=request_id, correlation_id=correlation_id)


@router.get(
    "/audit", response_model=AuditPageResponse, summary="Browse administrative audit records"
)
def list_audit(
    service: Annotated[AuditQueryService, Depends(get_audit_query_service)],
    user: Annotated[str | None, Query(max_length=128)] = None,
    action: Annotated[str | None, Query(max_length=128)] = None,
    resource: Annotated[str | None, Query(max_length=256)] = None,
    result: AuditResult | None = None,
    date_from: AwareDatetime | None = None,
    date_to: AwareDatetime | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AuditPageResponse:
    if date_from and date_to and date_from > date_to:
        raise administrative_error(AdministrativeErrorCode.invalid_request)
    page = service.list(
        AuditFilters(user, action, resource, result, date_from, date_to), limit=limit, offset=offset
    )
    return AuditPageResponse(
        items=[_audit_item(item) for item in page.items],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get(
    "/audit/rag",
    response_model=list[RagAuditEntryResponse],
    summary="Browse RAG debug audit records",
)
def list_rag_audit(
    reader: Annotated[Callable[[int], list[dict]], Depends(get_rag_audit_reader)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[RagAuditEntryResponse]:
    return [RagAuditEntryResponse.model_validate(item) for item in reader(limit)]


@router.get(
    "/audit/{entry_id}",
    response_model=AuditDetailResponse,
    summary="Read an administrative audit record",
)
def get_audit_entry(
    entry_id: UUID,
    service: Annotated[AuditQueryService, Depends(get_audit_query_service)],
) -> AuditDetailResponse:
    try:
        entry = service.get(entry_id)
    except AuditEntryNotFound as exc:
        raise administrative_error(AdministrativeErrorCode.audit_entry_not_found) from exc
    return AuditDetailResponse(
        **_audit_item(entry).model_dump(),
        actor=entry.actor,
        request_id=entry.request_id,
        correlation_id=entry.correlation_id,
        duration_ms=entry.duration_ms,
        metadata=entry.metadata,
    )


JobStatus = Literal["queued", "running", "completed", "failed", "cancelled"]


@router.get("/jobs", response_model=OperationalJobsResponse, summary="Browse background jobs")
def list_jobs(
    service: Annotated[JobOperationsService, Depends(get_job_operations_service)],
    status: JobStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OperationalJobsResponse:
    page = service.list(limit=limit, offset=offset, status=status)
    return OperationalJobsResponse(
        items=[_job(item) for item in page.items],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get(
    "/jobs/{job_id}", response_model=OperationalJobResponse, summary="Read a background job"
)
def get_job(
    job_id: UUID, service: Annotated[JobOperationsService, Depends(get_job_operations_service)]
) -> OperationalJobResponse:
    try:
        return _job(service.get(job_id))
    except OperationalJobNotFound as exc:
        raise administrative_error(AdministrativeErrorCode.operational_job_not_found) from exc


@router.get(
    "/summary",
    response_model=OperationsSummaryResponse,
    response_model_exclude={"request_id"},
    summary="Read the operational summary",
)
async def get_summary(
    summary_service: Annotated[OperationsSummaryService, Depends(get_operations_summary_service)],
    health_service: Annotated[HealthService, Depends(get_health_service)],
) -> OperationsSummaryResponse:
    diagnostic = await health_service.diagnose()
    summary = summary_service.get(health_override=HealthOverview(diagnostic.status.value))
    return OperationsSummaryResponse(
        generated_at=summary.generated_at,
        health=summary.health,
        maintenance=summary.maintenance,
        cache=SummaryCacheResponse(regions=summary.cache_regions),
        jobs=SummaryJobsResponse(running=summary.running_jobs, failed=summary.failed_jobs),
        audit=SummaryAuditResponse(today=summary.audit_today),
        assistants=SummaryAssistantsResponse(**vars(summary.assistants)),
        knowledge_sources=SummaryKnowledgeSourcesResponse(**vars(summary.knowledge_sources)),
        ingestion=SummaryIngestionResponse(**vars(summary.ingestion)),
    )


def _audit_item(entry: AuditEntry) -> AuditEntryResponse:
    return AuditEntryResponse(
        id=str(entry.id),
        timestamp=entry.timestamp,
        user=entry.actor,
        action=entry.action,
        resource=entry.resource,
        result=entry.result.value,
    )


def _job(job: OperationalJob) -> OperationalJobResponse:
    return OperationalJobResponse(
        id=str(job.id),
        status=job.status,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        duration_ms=job.duration_ms,
        retry_count=job.retry_count,
        last_error=job.last_error,
        execution_node=job.execution_node,
        job_type=job.job_type,
    )
