from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from assistant.domain.document_ingestion_job import DocumentIngestionJob, IngestionStep
from assistant.domain.ingestion_status import IngestionStatus


class CreateIngestionJobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_id: UUID


class DocumentIngestionJobResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    document_id: str
    status: IngestionStatus
    current_step: IngestionStep | None
    retry_count: int
    failure_code: str | None
    failure_message: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    updated_at: datetime

    @classmethod
    def from_job(cls, job: DocumentIngestionJob) -> "DocumentIngestionJobResponse":
        return cls.model_validate(job, from_attributes=True)


class DocumentIngestionJobListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[DocumentIngestionJobResponse]
    total: int
    limit: int
    offset: int
