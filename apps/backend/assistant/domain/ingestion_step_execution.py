from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from uuid import UUID

from assistant.domain.document_ingestion_job import IngestionStep


class IngestionStepExecutionStatus(str, Enum):
    running = "running"
    completed = "completed"
    failed = "failed"
    interrupted = "interrupted"


@dataclass(frozen=True)
class IngestionStepExecution:
    id: UUID
    ingestion_job_id: UUID
    step: IngestionStep
    attempt_number: int
    status: IngestionStepExecutionStatus
    started_at: datetime
    completed_at: datetime | None = None
    duration_ms: int | None = None
    failure_code: str | None = None
    retryable: bool | None = None

    def __post_init__(self) -> None:
        if self.attempt_number < 1:
            raise ValueError("Step attempt numbers start at one.")
        if self.duration_ms is not None and self.duration_ms < 0:
            raise ValueError("Step duration cannot be negative.")
        for timestamp in (self.started_at, self.completed_at):
            if timestamp is not None and (
                timestamp.tzinfo is None or timestamp.utcoffset() is None
            ):
                raise ValueError("Step execution timestamps must be timezone-aware.")
