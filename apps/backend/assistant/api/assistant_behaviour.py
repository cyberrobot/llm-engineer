import json
from collections.abc import Iterator
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from admin_auth.dependencies import require_administrator_role, require_trusted_admin_origin
from assistant.api.dependencies import (
    get_assistant_behaviour_service,
    get_assistant_preview_chat_service,
)
from assistant.application.assistant_behaviour_service import AssistantBehaviourService
from assistant.application.public_chat import (
    AssistantPreviewChatService,
    PreparedPublicChat,
    PublicChatInputLimitExceeded,
    PublicChatRequestTimedOut,
)
from assistant.domain.assistant_behaviour import AssistantBehaviourState
from assistant.domain.assistant_behaviour_repository import (
    AssistantBehaviourNotFound,
    AssistantBehaviourPublishConflict,
    AssistantBehaviourUpdateConflict,
)
from assistant.domain.assistant_repository import AssistantNotFound
from assistant.schemas.assistant_admin import AssistantAdminErrorResponse
from assistant.schemas.assistant_behaviour import (
    AssistantBehaviourDraftResponse,
    AssistantBehaviourPublishedResponse,
    AssistantBehaviourStateResponse,
    AssistantPreviewChatRequest,
    PublishAssistantBehaviourRequest,
    UpdateAssistantBehaviourRequest,
)

router = APIRouter(
    prefix="/admin/assistants",
    tags=["administrator assistant behaviour"],
    dependencies=[Depends(require_administrator_role)],
)

ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"model": AssistantAdminErrorResponse, "description": "Authentication required"},
    403: {"model": AssistantAdminErrorResponse, "description": "Trusted administrator required"},
    404: {"model": AssistantAdminErrorResponse, "description": "Assistant not found"},
    409: {"model": AssistantAdminErrorResponse, "description": "Behaviour conflict"},
    422: {"model": AssistantAdminErrorResponse, "description": "Invalid behaviour or chat input"},
}

PREVIEW_ERROR_RESPONSES = {
    **ERROR_RESPONSES,
    504: {"model": AssistantAdminErrorResponse, "description": "Preview preparation timed out"},
}


def _error(code: str, message: str, status_code: int) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def _response(state: AssistantBehaviourState) -> AssistantBehaviourStateResponse:
    return AssistantBehaviourStateResponse(
        assistant_id=state.assistant_id,
        draft=AssistantBehaviourDraftResponse(
            revision=state.draft.revision,
            instructions=state.draft.instructions,
            welcome_message=state.draft.welcome_message,
            input_placeholder=state.draft.input_placeholder,
            suggested_questions=list(state.draft.suggested_questions),
            created_at=state.draft.created_at,
        ),
        published=(
            AssistantBehaviourPublishedResponse(
                revision=state.published.revision,
                published_at=state.published_at,
            )
            if state.published is not None and state.published_at is not None
            else None
        ),
        has_unpublished_changes=state.has_unpublished_changes,
        concurrency_token=state.concurrency_token,
    )


@router.get(
    "/{assistant_id}/behaviour",
    response_model=AssistantBehaviourStateResponse,
    responses=ERROR_RESPONSES,
    description="Returns the saved editable draft, publication metadata, and opaque concurrency token.",
)
def get_behaviour(
    assistant_id: UUID,
    service: Annotated[AssistantBehaviourService, Depends(get_assistant_behaviour_service)],
) -> AssistantBehaviourStateResponse:
    try:
        return _response(service.get_state(assistant_id))
    except (AssistantNotFound, AssistantBehaviourNotFound) as exc:
        raise _error("assistant_not_found", "Assistant not found.", 404) from exc


@router.put(
    "/{assistant_id}/behaviour",
    response_model=AssistantBehaviourStateResponse,
    responses=ERROR_RESPONSES,
    dependencies=[Depends(require_trusted_admin_origin)],
    description="Saves a complete draft with optimistic concurrency. Saving does not publish it.",
)
def save_behaviour(
    assistant_id: UUID,
    request: UpdateAssistantBehaviourRequest,
    service: Annotated[AssistantBehaviourService, Depends(get_assistant_behaviour_service)],
) -> AssistantBehaviourStateResponse:
    try:
        return _response(
            service.save_draft(
                assistant_id,
                concurrency_token=request.concurrency_token,
                instructions=request.instructions,
                welcome_message=request.welcome_message,
                input_placeholder=request.input_placeholder,
                suggested_questions=tuple(request.suggested_questions),
            )
        )
    except AssistantNotFound as exc:
        raise _error("assistant_not_found", "Assistant not found.", 404) from exc
    except AssistantBehaviourUpdateConflict as exc:
        raise _error(
            "assistant_behaviour_update_conflict",
            "Assistant behaviour was updated concurrently.",
            409,
        ) from exc
    except ValueError as exc:
        raise _error("assistant_behaviour_invalid", str(exc), 422) from exc


@router.post(
    "/{assistant_id}/behaviour/publish",
    response_model=AssistantBehaviourStateResponse,
    responses=ERROR_RESPONSES,
    dependencies=[Depends(require_trusted_admin_origin)],
    description="Atomically publishes the exact current saved draft; it does not activate or expose the Assistant.",
)
def publish_behaviour(
    assistant_id: UUID,
    request: PublishAssistantBehaviourRequest,
    service: Annotated[AssistantBehaviourService, Depends(get_assistant_behaviour_service)],
) -> AssistantBehaviourStateResponse:
    try:
        return _response(
            service.publish(
                assistant_id,
                concurrency_token=request.concurrency_token,
                draft_revision=request.draft_revision,
            )
        )
    except AssistantNotFound as exc:
        raise _error("assistant_not_found", "Assistant not found.", 404) from exc
    except AssistantBehaviourPublishConflict as exc:
        raise _error(
            "assistant_behaviour_publish_conflict",
            "The requested draft is no longer the current saved draft.",
            409,
        ) from exc


def _preview_stream(session: PreparedPublicChat) -> Iterator[str]:
    events = session.events()
    try:
        for event in events:
            data = json.dumps(event.payload, ensure_ascii=False, separators=(",", ":"))
            yield f"event: {event.type}\ndata: {data}\n\n"
    finally:
        close = getattr(events, "close", None)
        if close is not None:
            close()


@router.post(
    "/{assistant_id}/preview/chat",
    response_class=StreamingResponse,
    responses=PREVIEW_ERROR_RESPONSES,
    dependencies=[Depends(require_trusted_admin_origin)],
    description="Streams grounded chat using the saved draft without publishing or changing availability.",
)
def preview_chat(
    assistant_id: UUID,
    request: AssistantPreviewChatRequest,
    service: Annotated[AssistantPreviewChatService, Depends(get_assistant_preview_chat_service)],
) -> StreamingResponse:
    try:
        session = service.prepare(assistant_id, request)
    except AssistantNotFound as exc:
        raise _error("assistant_not_found", "Assistant not found.", 404) from exc
    except AssistantBehaviourNotFound as exc:
        raise _error(
            "assistant_preview_unavailable", "Assistant preview is unavailable.", 409
        ) from exc
    except PublicChatInputLimitExceeded as exc:
        raise _error("input_token_limit_exceeded", "The chat input is too large.", 422) from exc
    except PublicChatRequestTimedOut as exc:
        raise _error("request_timed_out", "The response could not be completed.", 504) from exc
    return StreamingResponse(
        _preview_stream(session),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
