from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from admin_auth.dependencies import require_administrator_role, require_trusted_admin_origin
from assistant.api.dependencies import get_assistant_administration_service
from assistant.application.assistant_admin_service import (
    AssistantAdministrationService,
    ProtectedAssistantDeletion,
)
from assistant.domain.assistant import Assistant, AssistantStatus, AssistantVisibility
from assistant.domain.assistant_repository import (
    AssistantConcurrentUpdate,
    AssistantDeletionBlocked,
    AssistantNotFound,
    DuplicateAssistantSlug,
)
from assistant.schemas.assistant_admin import (
    AssistantAdminErrorResponse,
    AssistantDetailResponse,
    AssistantListResponse,
    AssistantResponse,
    CreateAssistantRequest,
    UpdateAssistantRequest,
)

router = APIRouter(
    prefix="/admin/assistants",
    tags=["administrator assistants"],
    dependencies=[Depends(require_administrator_role)],
)

ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"model": AssistantAdminErrorResponse, "description": "Authentication required"},
    403: {
        "model": AssistantAdminErrorResponse,
        "description": "Administrator or trusted origin required",
    },
    404: {"model": AssistantAdminErrorResponse, "description": "Assistant not found"},
    409: {"model": AssistantAdminErrorResponse, "description": "Assistant lifecycle conflict"},
    422: {"model": AssistantAdminErrorResponse, "description": "Request validation failed"},
}


def error(code: str, message: str, status_code: int) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def response(a: Assistant) -> AssistantResponse:
    return AssistantResponse(
        id=a.id,
        slug=a.slug,
        name=a.name,
        status=a.status,
        visibility=a.visibility,
        created_at=a.created_at,
        updated_at=a.updated_at,
        concurrency_token=a.updated_at,
    )


@router.get("", response_model=AssistantListResponse, responses=ERROR_RESPONSES)
def list_assistants(
    service: Annotated[
        AssistantAdministrationService, Depends(get_assistant_administration_service)
    ],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    status_filter: Annotated[AssistantStatus | None, Query(alias="status")] = None,
    visibility: AssistantVisibility | None = None,
) -> AssistantListResponse:
    items, total = service.list_assistants(
        limit=limit, offset=offset, status=status_filter, visibility=visibility
    )
    return AssistantListResponse(
        items=[response(a) for a in items], total=total, limit=limit, offset=offset
    )


@router.get("/{assistant_id}", response_model=AssistantDetailResponse, responses=ERROR_RESPONSES)
def detail(
    assistant_id: UUID,
    service: Annotated[
        AssistantAdministrationService, Depends(get_assistant_administration_service)
    ],
) -> AssistantDetailResponse:
    try:
        view = service.get_assistant(assistant_id)
    except AssistantNotFound as exc:
        raise error("assistant_not_found", "Assistant not found.", 404) from exc
    return AssistantDetailResponse(
        **response(view.assistant).model_dump(),
        knowledge_source_count=view.knowledge_source_count,
        deletion_allowed=view.deletion_allowed,
    )


@router.post(
    "",
    status_code=201,
    response_model=AssistantResponse,
    responses=ERROR_RESPONSES,
    description="Creates an assistant. Status defaults to inactive and visibility to private; the slug is immutable.",
    dependencies=[Depends(require_trusted_admin_origin)],
)
def create(
    request: CreateAssistantRequest,
    service: Annotated[
        AssistantAdministrationService, Depends(get_assistant_administration_service)
    ],
    response_header: Response,
) -> AssistantResponse:
    try:
        assistant = service.create_assistant(
            slug=request.slug,
            name=request.name,
            status=request.status,
            visibility=request.visibility,
        )
    except DuplicateAssistantSlug as exc:
        raise error("assistant_slug_conflict", "Assistant slug already exists.", 409) from exc
    except ValueError as exc:
        raise error("invalid_request", str(exc), 400) from exc
    response_header.headers["Location"] = f"/admin/assistants/{assistant.id}"
    return response(assistant)


@router.patch(
    "/{assistant_id}",
    response_model=AssistantResponse,
    responses=ERROR_RESPONSES,
    description="Updates mutable fields using the detail response's timestamp concurrency token.",
    dependencies=[Depends(require_trusted_admin_origin)],
)
def update(
    assistant_id: UUID,
    request: UpdateAssistantRequest,
    service: Annotated[
        AssistantAdministrationService, Depends(get_assistant_administration_service)
    ],
) -> AssistantResponse:
    try:
        return response(
            service.update_assistant(
                assistant_id,
                concurrency_token=request.concurrency_token,
                name=request.name,
                status=request.status,
                visibility=request.visibility,
            )
        )
    except AssistantNotFound as exc:
        raise error("assistant_not_found", "Assistant not found.", 404) from exc
    except AssistantConcurrentUpdate as exc:
        raise error(
            "assistant_update_conflict", "Assistant was updated concurrently.", 409
        ) from exc
    except ValueError as exc:
        raise error("invalid_request", str(exc), 400) from exc


@router.delete(
    "/{assistant_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=ERROR_RESPONSES,
    description="Deletes an unused non-Redmoor assistant without cascading assistant-owned state.",
    dependencies=[Depends(require_trusted_admin_origin)],
)
def delete(
    assistant_id: UUID,
    service: Annotated[
        AssistantAdministrationService, Depends(get_assistant_administration_service)
    ],
) -> Response:
    try:
        service.delete_assistant(assistant_id)
    except AssistantNotFound as exc:
        raise error("assistant_not_found", "Assistant not found.", 404) from exc
    except ProtectedAssistantDeletion as exc:
        raise error("protected_assistant", "The seeded assistant cannot be deleted.", 409) from exc
    except AssistantDeletionBlocked as exc:
        raise error("assistant_has_dependencies", "Assistant has dependent records.", 409) from exc
    return Response(status_code=204)
