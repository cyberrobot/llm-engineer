from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from assistant.domain.assistant_behaviour import (
    MAX_BEHAVIOUR_INSTRUCTIONS_LENGTH,
    MAX_INPUT_PLACEHOLDER_LENGTH,
    MAX_SUGGESTED_QUESTIONS,
    MAX_WELCOME_MESSAGE_LENGTH,
)
from assistant.schemas.public_chat import PublicChatRequest


class AssistantBehaviourDraftResponse(BaseModel):
    revision: int
    instructions: str
    welcome_message: str
    input_placeholder: str
    suggested_questions: list[str]
    created_at: datetime
    updated_at: datetime


class AssistantBehaviourPublishedResponse(BaseModel):
    revision: int
    published_at: datetime


class AssistantBehaviourStateResponse(BaseModel):
    assistant_id: UUID
    draft: AssistantBehaviourDraftResponse
    published: AssistantBehaviourPublishedResponse | None
    has_unpublished_changes: bool
    concurrency_token: str


class UpdateAssistantBehaviourRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    concurrency_token: str = Field(min_length=1, max_length=100)
    instructions: str = Field(min_length=1, max_length=MAX_BEHAVIOUR_INSTRUCTIONS_LENGTH)
    welcome_message: str = Field(max_length=MAX_WELCOME_MESSAGE_LENGTH)
    input_placeholder: str = Field(min_length=1, max_length=MAX_INPUT_PLACEHOLDER_LENGTH)
    suggested_questions: list[str] = Field(max_length=MAX_SUGGESTED_QUESTIONS)


class PublishAssistantBehaviourRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    concurrency_token: str = Field(min_length=1, max_length=100)
    draft_revision: int = Field(ge=1)


class AssistantPreviewChatRequest(PublicChatRequest):
    """A bounded chat request executed only against the server-authoritative saved draft."""

    pass
