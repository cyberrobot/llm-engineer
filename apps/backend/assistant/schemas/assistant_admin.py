from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from assistant.domain.assistant import (
    MAX_ASSISTANT_NAME_LENGTH,
    MAX_ASSISTANT_SLUG_LENGTH,
    AssistantStatus,
    AssistantVisibility,
)


class CreateAssistantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    slug: str = Field(
        min_length=1, max_length=MAX_ASSISTANT_SLUG_LENGTH, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
    )
    name: str = Field(min_length=1, max_length=MAX_ASSISTANT_NAME_LENGTH)
    status: AssistantStatus = AssistantStatus.inactive
    visibility: AssistantVisibility = AssistantVisibility.private


class UpdateAssistantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    concurrency_token: datetime
    name: str | None = Field(default=None, min_length=1, max_length=MAX_ASSISTANT_NAME_LENGTH)
    status: AssistantStatus | None = None
    visibility: AssistantVisibility | None = None

    @model_validator(mode="after")
    def non_empty(self):
        if self.name is None and self.status is None and self.visibility is None:
            raise ValueError("At least one mutable field is required.")
        return self


class AssistantResponse(BaseModel):
    id: UUID
    slug: str
    name: str
    status: AssistantStatus
    visibility: AssistantVisibility
    created_at: datetime
    updated_at: datetime
    concurrency_token: datetime


class AssistantDetailResponse(AssistantResponse):
    knowledge_source_count: int
    deletion_allowed: bool


class AssistantListResponse(BaseModel):
    items: list[AssistantResponse]
    total: int
    limit: int
    offset: int
