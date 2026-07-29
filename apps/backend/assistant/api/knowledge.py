from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, status

from assistant.api.dependencies import get_ingestion_service
from assistant.application.ingestion_service import IngestionService
from assistant.schemas import (
    ErrorResponse,
    IngestionJobResponse,
    KnowledgeStatusResponse,
    StartIngestionRequest,
)

router = APIRouter(prefix="/assistant/knowledge", tags=["assistant knowledge"])


@router.post(
    "/ingestions",
    response_model=IngestionJobResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start a knowledge ingestion job",
)
def start_ingestion(
    request: StartIngestionRequest,
    service: Annotated[IngestionService, Depends(get_ingestion_service)],
) -> IngestionJobResponse:
    job = service.start_ingestion(str(request.url))
    return IngestionJobResponse.from_job(job)


@router.get(
    "/ingestions/{jobId}",
    response_model=IngestionJobResponse,
    responses={404: {"model": ErrorResponse, "description": "Ingestion job not found"}},
    summary="Get a knowledge ingestion job",
)
def get_ingestion(
    job_id: Annotated[UUID, Path(alias="jobId")],
    service: Annotated[IngestionService, Depends(get_ingestion_service)],
) -> IngestionJobResponse:
    return IngestionJobResponse.from_job(service.get_job(job_id))


@router.get(
    "/status",
    response_model=KnowledgeStatusResponse,
    summary="Get Assistant knowledge status",
)
def get_knowledge_status(
    service: Annotated[IngestionService, Depends(get_ingestion_service)],
) -> KnowledgeStatusResponse:
    return KnowledgeStatusResponse.from_status(service.get_knowledge_status())
