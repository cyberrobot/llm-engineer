from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status

from assistant.api.dependencies import get_document_ingestion_job_service
from assistant.application.ingestion_job_service import (
    DocumentIngestionJobService,
    DocumentNotFound,
    IdempotencyKeyConflict,
    IngestionJobNotFound,
    IngestionJobUnavailable,
    InvalidIdempotencyKey,
)
from assistant.domain.ingestion_status import IngestionStatus
from assistant.schemas.document_ingestion_job import (
    CreateIngestionJobRequest,
    DocumentIngestionJobListResponse,
    DocumentIngestionJobResponse,
)

router = APIRouter(prefix="/ingestion/jobs", tags=["ingestion jobs"])


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


@router.post("", response_model=DocumentIngestionJobResponse, status_code=status.HTTP_201_CREATED)
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
) -> DocumentIngestionJobListResponse:
    if status_filter is IngestionStatus.pending:
        raise _error(422, "invalid_ingestion_status", "Invalid ingestion status filter.")
    try:
        page = service.list(
            limit=limit,
            offset=offset,
            status=status_filter,
            document_id=str(document_id) if document_id else None,
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
