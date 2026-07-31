from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status

from assistant.api.dependencies import (
    get_document_ingestion_job_service,
    get_ingestion_pipeline_runner,
    get_ingestion_step_execution_repository,
)
from assistant.api.ingest import require_ingest_api_key
from assistant.application.ingestion_job_service import (
    DocumentIngestionJobService,
    DocumentNotFound,
    IdempotencyKeyConflict,
    IngestionJobNotFound,
    IngestionJobUnavailable,
    InvalidIdempotencyKey,
)
from assistant.application.ingestion_pipeline import IngestionPipelineRunner
from assistant.domain.document_ingestion_job import IngestionStep
from assistant.domain.ingestion_status import IngestionStatus
from assistant.infrastructure.repositories.ingestion_observability import (
    IngestionStepExecutionRepository,
)
from assistant.schemas.document_ingestion_job import (
    CreateIngestionJobRequest,
    DocumentIngestionJobListResponse,
    DocumentIngestionJobResponse,
    IngestionPipelineResultResponse,
    IngestionStepExecutionResponse,
)


def require_ingestion_jobs_api_key(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> None:
    require_ingest_api_key(x_api_key)


router = APIRouter(
    prefix="/ingestion/jobs",
    tags=["ingestion jobs"],
    dependencies=[Depends(require_ingestion_jobs_api_key)],
)


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


@router.post("", response_model=DocumentIngestionJobResponse, status_code=status.HTTP_202_ACCEPTED)
def create_ingestion_job(
    request: CreateIngestionJobRequest,
    service: Annotated[DocumentIngestionJobService, Depends(get_document_ingestion_job_service)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> DocumentIngestionJobResponse:
    try:
        job = service.create(str(request.document_id), idempotency_key=idempotency_key)
    except InvalidIdempotencyKey as exc:
        raise _error(400, "invalid_idempotency_key", str(exc)) from exc
    except DocumentNotFound as exc:
        raise _error(404, "document_not_found", "Document not found.") from exc
    except IdempotencyKeyConflict as exc:
        raise _error(409, "idempotency_key_conflict", str(exc)) from exc
    except IngestionJobUnavailable as exc:
        raise _error(503, "ingestion_job_unavailable", str(exc)) from exc
    return DocumentIngestionJobResponse.from_job(job)


@router.get("", response_model=DocumentIngestionJobListResponse)
def list_ingestion_jobs(
    service: Annotated[DocumentIngestionJobService, Depends(get_document_ingestion_job_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    status_filter: Annotated[IngestionStatus | None, Query(alias="status")] = None,
    document_id: Annotated[UUID | None, Query()] = None,
    created_from: Annotated[datetime | None, Query()] = None,
    created_to: Annotated[datetime | None, Query()] = None,
    failed_step: Annotated[IngestionStep | None, Query()] = None,
) -> DocumentIngestionJobListResponse:
    if status_filter is IngestionStatus.pending:
        raise _error(422, "invalid_ingestion_status", "Invalid ingestion status filter.")
    if created_from is not None and created_to is not None and created_from > created_to:
        raise _error(422, "invalid_created_range", "created_from must not follow created_to.")
    try:
        page = service.list(
            limit=limit,
            offset=offset,
            status=status_filter,
            document_id=str(document_id) if document_id else None,
            created_from=created_from,
            created_to=created_to,
            failed_step=failed_step,
        )
    except IngestionJobUnavailable as exc:
        raise _error(503, "ingestion_job_unavailable", str(exc)) from exc
    return DocumentIngestionJobListResponse(
        items=[DocumentIngestionJobResponse.from_job(job) for job in page.items],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/{job_id}", response_model=DocumentIngestionJobResponse)
def get_ingestion_job(
    job_id: UUID,
    service: Annotated[DocumentIngestionJobService, Depends(get_document_ingestion_job_service)],
) -> DocumentIngestionJobResponse:
    try:
        job = service.get(job_id)
    except IngestionJobNotFound as exc:
        raise _error(404, "ingestion_job_not_found", "Ingestion job not found.") from exc
    except IngestionJobUnavailable as exc:
        raise _error(503, "ingestion_job_unavailable", str(exc)) from exc
    return DocumentIngestionJobResponse.from_job(job)


@router.get("/{job_id}/steps", response_model=list[IngestionStepExecutionResponse])
def list_ingestion_job_steps(
    job_id: UUID,
    service: Annotated[DocumentIngestionJobService, Depends(get_document_ingestion_job_service)],
    repository: Annotated[
        IngestionStepExecutionRepository,
        Depends(get_ingestion_step_execution_repository),
    ],
) -> list[IngestionStepExecutionResponse]:
    try:
        service.get(job_id)
    except IngestionJobNotFound as exc:
        raise _error(404, "ingestion_job_not_found", "Ingestion job not found.") from exc
    except IngestionJobUnavailable as exc:
        raise _error(503, "ingestion_job_unavailable", str(exc)) from exc
    return [
        IngestionStepExecutionResponse.from_execution(execution)
        for execution in repository.list_for_job(job_id)
    ]


@router.post("/{job_id}/run", response_model=IngestionPipelineResultResponse)
def run_ingestion_job(
    job_id: UUID,
    runner: Annotated[IngestionPipelineRunner, Depends(get_ingestion_pipeline_runner)],
) -> IngestionPipelineResultResponse:
    result = runner.run(job_id)
    if result.failure_code == "ingestion_job_not_found":
        raise _error(404, result.failure_code, result.failure_message or "Ingestion job not found.")
    if result.failure_code in {
        "ingestion_job_not_runnable",
        "invalid_ingestion_job_checkpoint",
    }:
        raise _error(409, result.failure_code, result.failure_message or "Ingestion job conflict.")
    return IngestionPipelineResultResponse.from_result(result)
