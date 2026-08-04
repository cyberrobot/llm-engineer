from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status

from admin_auth.dependencies import require_administrator_role, require_trusted_admin_origin
from assistant.api.dependencies import get_knowledge_source_service
from assistant.application.knowledge_source_service import (
    ActiveIngestionConflict,
    IdempotencyConflict,
    KnowledgeSourceNotFound,
    KnowledgeSourceService,
)
from assistant.schemas.knowledge_source import (
    CreateKnowledgeSourceRequest,
    KnowledgeSourceListResponse,
    KnowledgeSourceResponse,
    UpdateKnowledgeSourceRequest,
)

router = APIRouter(
    prefix="/admin/assistants/{assistant_id}/knowledge-sources",
    tags=["administrator knowledge sources"],
    dependencies=[Depends(require_administrator_role)],
)


def _error(code, message, status_code):
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def _response(view, *, detail=False, reused=False):
    source = view.source
    return KnowledgeSourceResponse(
        id=source.id,
        assistant_id=source.assistant_id,
        source_type=source.source_type,
        name=source.name,
        retrieval_state=source.retrieval_state,
        url=source.url,
        direct_text=source.direct_text if detail else None,
        document_id=source.document_id,
        created_at=source.created_at,
        updated_at=source.updated_at,
        latest_ingestion=None
        if view.latest_job is None
        else __import__(
            "assistant.schemas.knowledge_source", fromlist=["KnowledgeSourceJobResponse"]
        ).KnowledgeSourceJobResponse.from_job(view.latest_job),
        active_job_reused=reused,
    )


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=KnowledgeSourceResponse,
    dependencies=[Depends(require_trusted_admin_origin)],
)
def create(
    assistant_id: UUID,
    request: CreateKnowledgeSourceRequest,
    service: Annotated[KnowledgeSourceService, Depends(get_knowledge_source_service)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
):
    try:
        view, reused = service.create(
            assistant_id,
            source_type=request.source_type,
            name=request.name,
            direct_text=request.direct_text,
            url=request.url,
            idempotency_key=idempotency_key,
        )
        return _response(view, detail=True, reused=reused)
    except KnowledgeSourceNotFound as exc:
        raise _error("assistant_not_found", "Assistant not found.", 404) from exc
    except IdempotencyConflict as exc:
        raise _error("idempotency_key_conflict", str(exc), 409) from exc
    except ValueError as exc:
        raise _error("invalid_request", str(exc), 400) from exc


@router.get("", response_model=KnowledgeSourceListResponse)
def list_sources(
    assistant_id: UUID,
    service: Annotated[KnowledgeSourceService, Depends(get_knowledge_source_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    try:
        views, total = service.list(assistant_id, limit=limit, offset=offset)
    except KnowledgeSourceNotFound as exc:
        raise _error("assistant_not_found", "Assistant not found.", 404) from exc
    return KnowledgeSourceListResponse(
        items=[_response(view) for view in views], total=total, limit=limit, offset=offset
    )


@router.get("/{source_id}", response_model=KnowledgeSourceResponse)
def detail(
    assistant_id: UUID,
    source_id: UUID,
    service: Annotated[KnowledgeSourceService, Depends(get_knowledge_source_service)],
):
    try:
        return _response(service.get(assistant_id, source_id), detail=True)
    except KnowledgeSourceNotFound as exc:
        raise _error("knowledge_source_not_found", "Knowledge source not found.", 404) from exc


@router.patch(
    "/{source_id}",
    response_model=KnowledgeSourceResponse,
    dependencies=[Depends(require_trusted_admin_origin)],
)
def update(
    assistant_id: UUID,
    source_id: UUID,
    request: UpdateKnowledgeSourceRequest,
    service: Annotated[KnowledgeSourceService, Depends(get_knowledge_source_service)],
):
    try:
        return _response(
            service.update(assistant_id, source_id, request.retrieval_state), detail=True
        )
    except KnowledgeSourceNotFound as exc:
        raise _error("knowledge_source_not_found", "Knowledge source not found.", 404) from exc


@router.post(
    "/{source_id}/reingestions",
    status_code=202,
    response_model=KnowledgeSourceResponse,
    dependencies=[Depends(require_trusted_admin_origin)],
)
def reingest(
    assistant_id: UUID,
    source_id: UUID,
    service: Annotated[KnowledgeSourceService, Depends(get_knowledge_source_service)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
):
    try:
        view, reused = service.reingest(assistant_id, source_id, idempotency_key=idempotency_key)
        return _response(view, detail=True, reused=reused)
    except KnowledgeSourceNotFound as exc:
        raise _error("knowledge_source_not_found", "Knowledge source not found.", 404) from exc


@router.delete(
    "/{source_id}", status_code=204, dependencies=[Depends(require_trusted_admin_origin)]
)
def delete(
    assistant_id: UUID,
    source_id: UUID,
    service: Annotated[KnowledgeSourceService, Depends(get_knowledge_source_service)],
):
    try:
        service.delete(assistant_id, source_id)
        return Response(status_code=204)
    except ActiveIngestionConflict as exc:
        raise _error(
            "active_ingestion", "Knowledge source has an active ingestion job.", 409
        ) from exc
    except KnowledgeSourceNotFound as exc:
        raise _error("knowledge_source_not_found", "Knowledge source not found.", 404) from exc
