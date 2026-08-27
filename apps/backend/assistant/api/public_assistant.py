import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response

from assistant.api.dependencies import get_public_assistant_configuration_service
from assistant.application.public_assistant import PublicAssistantConfigurationService
from assistant.domain.assistant_behaviour_repository import AssistantBehaviourNotFound
from assistant.domain.assistant_repository import AssistantNotFound
from assistant.schemas.public_assistant import PublicAssistantConfigurationResponse
from assistant.schemas.public_chat import PublicChatErrorResponse

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "/public/assistants/{assistant_slug}",
    response_model=PublicAssistantConfigurationResponse,
    responses={
        404: {"model": PublicChatErrorResponse, "description": "Assistant not found"},
        500: {"model": PublicChatErrorResponse, "description": "Configuration unavailable"},
        503: {"model": PublicChatErrorResponse, "description": "Public assistant disabled"},
    },
    summary="Get published public assistant configuration",
    tags=["public assistant"],
    openapi_extra={"security": []},
)
def public_assistant_configuration(
    assistant_slug: str,
    response: Response,
    service: Annotated[
        PublicAssistantConfigurationService,
        Depends(get_public_assistant_configuration_service),
    ],
) -> PublicAssistantConfigurationResponse:
    try:
        configuration = service.get(assistant_slug)
    except (AssistantNotFound, AssistantBehaviourNotFound) as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": "assistant_not_found", "message": "Assistant not found."},
            headers={"Cache-Control": "no-store"},
        ) from exc
    except Exception as exc:
        logger.error(
            "Public assistant configuration failed",
            extra={"assistant_slug": assistant_slug},
        )
        raise HTTPException(
            status_code=500,
            detail={
                "code": "public_assistant_unavailable",
                "message": "Assistant configuration is unavailable.",
            },
            headers={"Cache-Control": "no-store"},
        ) from exc
    response.headers["Cache-Control"] = "no-store"
    return PublicAssistantConfigurationResponse.from_configuration(configuration)
