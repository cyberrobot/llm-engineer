from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from assistant.domain.assistant import DocumentRetrievalState
from assistant.domain.document_ingestion_job import DocumentIngestionJob, IngestionStep
from assistant.domain.ingestion_status import IngestionStatus
from assistant.domain.knowledge_source import MAX_DIRECT_TEXT_CHARACTERS, KnowledgeSourceType


class CreateKnowledgeSourceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_type: KnowledgeSourceType
    name: str = Field(min_length=1, max_length=255)
    direct_text: str | None = Field(default=None, max_length=MAX_DIRECT_TEXT_CHARACTERS)
    url: str | None = None

    @model_validator(mode="after")
    def payload(self):
        if self.source_type is KnowledgeSourceType.direct_text and (
            not self.direct_text or not self.direct_text.strip() or self.url is not None
        ):
            raise ValueError("direct_text source requires only direct_text")
        if self.source_type is KnowledgeSourceType.url and (
            not self.url or self.direct_text is not None
        ):
            raise ValueError("url source requires only url")
        return self


class UpdateKnowledgeSourceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    retrieval_state: DocumentRetrievalState


class KnowledgeSourceJobResponse(BaseModel):
    id: UUID
    status: IngestionStatus
    current_step: IngestionStep | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    failure_code: str | None
    failure_message: str | None

    @classmethod
    def from_job(cls, job: DocumentIngestionJob):
        return cls(
            id=job.id,
            status=job.status,
            current_step=job.current_step,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            failure_code=job.failure_code,
            failure_message=job.failure_message,
        )


class KnowledgeSourceResponse(BaseModel):
    id: UUID
    assistant_id: UUID
    source_type: KnowledgeSourceType
    name: str
    retrieval_state: DocumentRetrievalState
    url: str | None
    direct_text: str | None = None
    document_id: str
    created_at: datetime
    updated_at: datetime
    latest_ingestion: KnowledgeSourceJobResponse | None
    active_job_reused: bool = False


class KnowledgeSourceListResponse(BaseModel):
    items: list[KnowledgeSourceResponse]
    total: int
    limit: int
    offset: int
