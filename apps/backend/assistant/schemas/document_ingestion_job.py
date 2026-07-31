from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from assistant.application.ingestion_observability import IngestionProgressCalculator
from assistant.application.ingestion_pipeline import IngestionPipelineResult
from assistant.domain.document_ingestion_job import DocumentIngestionJob, IngestionStep
from assistant.domain.ingestion_status import IngestionStatus
from assistant.domain.ingestion_step_execution import (
    IngestionStepExecution,
    IngestionStepExecutionStatus,
)


class CreateIngestionJobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_id: UUID


class DocumentIngestionJobResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    document_id: str
    status: IngestionStatus
    current_step: IngestionStep | None
    last_completed_step: IngestionStep | None
    retry_count: int
    current_step_attempt_count: int
    last_attempted_at: datetime | None
    failure_code: str | None
    failure_message: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    updated_at: datetime
    queued_at: datetime
    completed_step_count: int
    total_step_count: int
    progress_percent: int
    queue_wait_duration_ms: int | None
    processing_duration_ms: int | None
    total_duration_ms: int
    failure: "IngestionFailureResponse | None"

    @classmethod
    def from_job(cls, job: DocumentIngestionJob) -> "DocumentIngestionJobResponse":
        progress = IngestionProgressCalculator(tuple(IngestionStep)).calculate(job)
        failure = None
        if job.status is IngestionStatus.failed:
            failure = IngestionFailureResponse(
                failure_code=job.failure_code,
                failure_category=None,
                failed_step=job.current_step,
                retryable=None,
                retry_exhausted=None,
                safe_message=job.failure_message,
            )
        return cls.model_validate(
            {
                "id": job.id,
                "document_id": job.document_id,
                "status": job.status,
                "current_step": job.current_step,
                "last_completed_step": job.last_completed_step,
                "retry_count": job.retry_count,
                "current_step_attempt_count": job.current_step_attempt_count,
                "last_attempted_at": job.last_attempted_at,
                "failure_code": job.failure_code,
                "failure_message": job.failure_message,
                "created_at": job.created_at,
                "started_at": job.started_at,
                "completed_at": job.completed_at,
                "updated_at": job.updated_at,
                **progress.__dict__,
                "failure": failure,
            }
        )


class IngestionFailureResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    failure_code: str | None
    failure_category: str | None
    failed_step: IngestionStep | None
    retryable: bool | None
    retry_exhausted: bool | None
    safe_message: str | None


class DocumentIngestionJobListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[DocumentIngestionJobResponse]
    total: int
    limit: int
    offset: int


class IngestionStepExecutionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step: IngestionStep
    attempt_number: int
    status: IngestionStepExecutionStatus
    started_at: datetime
    completed_at: datetime | None
    duration_ms: int | None
    failure_code: str | None
    retryable: bool | None

    @classmethod
    def from_execution(cls, execution: IngestionStepExecution) -> "IngestionStepExecutionResponse":
        return cls.model_validate(execution, from_attributes=True)


class IngestionPipelineResultResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: UUID
    status: IngestionStatus | None
    succeeded: bool
    last_completed_step: IngestionStep | None
    failed_step: IngestionStep | None
    failure_code: str | None
    failure_message: str | None
    retryable: bool | None
    attempts_used: int
    retries_performed: int
    retry_exhausted: bool
    total_retries: int

    @classmethod
    def from_result(cls, result: IngestionPipelineResult) -> "IngestionPipelineResultResponse":
        return cls.model_validate(result, from_attributes=True)
