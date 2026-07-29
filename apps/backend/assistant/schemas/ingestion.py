from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from assistant.application.ingestion_service import KnowledgeStatus
from assistant.domain.ingestion_job import IngestionJob
from assistant.domain.ingestion_status import IngestionStatus


class StartIngestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: HttpUrl

    @field_validator("url")
    @classmethod
    def reject_credentials(cls, url: HttpUrl) -> HttpUrl:
        if url.username is not None or url.password is not None:
            raise ValueError("URL credentials are not allowed")
        return url


class IngestionJobResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    job_id: UUID = Field(alias="jobId")
    status: IngestionStatus
    source_url: str = Field(alias="sourceUrl")
    documents_discovered: int = Field(alias="documentsDiscovered")
    documents_processed: int = Field(alias="documentsProcessed")
    chunks_created: int = Field(alias="chunksCreated")
    error_message: str | None = Field(alias="error")
    created_at: datetime = Field(alias="createdAt")
    started_at: datetime | None = Field(alias="startedAt")
    completed_at: datetime | None = Field(alias="completedAt")

    @classmethod
    def from_job(cls, job: IngestionJob) -> "IngestionJobResponse":
        return cls.model_validate(
            {
                "jobId": job.id,
                "status": job.status,
                "sourceUrl": job.source_url,
                "documentsDiscovered": job.documents_discovered,
                "documentsProcessed": job.documents_processed,
                "chunksCreated": job.chunks_created,
                "error": job.error_message,
                "createdAt": job.created_at,
                "startedAt": job.started_at,
                "completedAt": job.completed_at,
            }
        )


class KnowledgeStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    documents: int
    chunks: int
    last_ingestion_at: datetime | None = Field(alias="lastIngestionAt")
    last_ingestion_status: IngestionStatus | None = Field(alias="lastIngestionStatus")

    @classmethod
    def from_status(cls, status: KnowledgeStatus) -> "KnowledgeStatusResponse":
        return cls.model_validate(
            {
                "documents": status.documents,
                "chunks": status.chunks,
                "lastIngestionAt": status.last_ingestion_at,
                "lastIngestionStatus": status.last_ingestion_status,
            }
        )
