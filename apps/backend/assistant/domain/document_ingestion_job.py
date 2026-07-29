from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from uuid import UUID, uuid4

from assistant.domain.ingestion_status import IngestionStatus


class InvalidDocumentIngestionJob(ValueError):
    """Raised when a document ingestion job violates a lifecycle invariant."""


class IngestionStep(str, Enum):
    parse = "parse"
    chunk = "chunk"
    embed = "embed"
    persist = "persist"


TERMINAL_STATUSES = frozenset(
    {IngestionStatus.completed, IngestionStatus.failed, IngestionStatus.cancelled}
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _require_aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise InvalidDocumentIngestionJob("Ingestion job timestamps must be timezone-aware.")


@dataclass
class DocumentIngestionJob:
    id: UUID
    document_id: str
    status: IngestionStatus
    current_step: IngestionStep | None
    retry_count: int
    failure_code: str | None
    failure_message: str | None
    idempotency_key: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    updated_at: datetime
    last_completed_step: IngestionStep | None = None
    current_step_attempt_count: int = 0
    last_attempted_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.document_id.strip():
            raise InvalidDocumentIngestionJob("An ingestion job requires a document identifier.")
        if self.retry_count < 0:
            raise InvalidDocumentIngestionJob("Ingestion job retry count cannot be negative.")
        if self.current_step_attempt_count < 0:
            raise InvalidDocumentIngestionJob("Current step attempt count cannot be negative.")
        for timestamp in (
            self.created_at,
            self.started_at,
            self.completed_at,
            self.updated_at,
            self.last_attempted_at,
        ):
            if timestamp is not None:
                _require_aware(timestamp)
        if self.updated_at < self.created_at:
            raise InvalidDocumentIngestionJob("updated_at cannot precede created_at.")
        self._validate_lifecycle()

    @classmethod
    def create(
        cls,
        document_id: str,
        *,
        idempotency_key: str | None = None,
        retry_count: int = 0,
        job_id: UUID | None = None,
        created_at: datetime | None = None,
    ) -> "DocumentIngestionJob":
        timestamp = created_at or utc_now()
        return cls(
            id=job_id or uuid4(),
            document_id=document_id,
            status=IngestionStatus.queued,
            current_step=None,
            retry_count=retry_count,
            failure_code=None,
            failure_message=None,
            idempotency_key=idempotency_key,
            created_at=timestamp,
            started_at=None,
            completed_at=None,
            updated_at=timestamp,
            last_completed_step=None,
            current_step_attempt_count=0,
            last_attempted_at=None,
        )

    def mark_running(self, *, at: datetime | None = None) -> None:
        self._transition(IngestionStatus.running, at=at)

    def mark_completed(self, *, at: datetime | None = None) -> None:
        self._transition(IngestionStatus.completed, at=at)
        self.current_step = None
        self.failure_code = None
        self.failure_message = None
        self.current_step_attempt_count = 0
        self.last_attempted_at = None

    def mark_failed(
        self,
        failure_code: str | None,
        failure_message: str | None,
        *,
        at: datetime | None = None,
    ) -> None:
        code = failure_code.strip() if failure_code else None
        message = failure_message.strip() if failure_message else None
        if not code and not message:
            raise InvalidDocumentIngestionJob("A failed job requires a failure code or message.")
        self._transition(IngestionStatus.failed, at=at)
        self.failure_code = code or None
        self.failure_message = message or None

    def mark_cancelled(self, *, at: datetime | None = None) -> None:
        self._transition(IngestionStatus.cancelled, at=at)

    def set_current_step(self, step: IngestionStep, *, at: datetime | None = None) -> None:
        self._require_non_terminal()
        if self.current_step is not step:
            self.current_step_attempt_count = 0
            self.last_attempted_at = None
            self.failure_code = None
            self.failure_message = None
        self.current_step = step
        self._touch(at)

    def begin_step_attempt(self, *, at: datetime | None = None) -> None:
        self._require_non_terminal()
        if self.status is not IngestionStatus.running or self.current_step is None:
            raise InvalidDocumentIngestionJob("A running current step is required for an attempt.")
        timestamp = self._validated_operation_time(at)
        self.current_step_attempt_count += 1
        self.last_attempted_at = timestamp
        self.updated_at = timestamp

    def schedule_retry(
        self,
        failure_code: str,
        failure_message: str,
        *,
        at: datetime | None = None,
    ) -> None:
        self._require_non_terminal()
        if self.status is not IngestionStatus.running or self.current_step_attempt_count < 1:
            raise InvalidDocumentIngestionJob("A failed running attempt is required for a retry.")
        timestamp = self._validated_operation_time(at)
        self.retry_count += 1
        self.current_step_attempt_count += 1
        self.failure_code = failure_code.strip()
        self.failure_message = failure_message.strip()
        self.last_attempted_at = timestamp
        self.updated_at = timestamp

    def mark_step_completed(self, step: IngestionStep, *, at: datetime | None = None) -> None:
        self._require_non_terminal()
        if self.status is not IngestionStatus.running:
            raise InvalidDocumentIngestionJob("Only a running job can complete a step.")
        if self.current_step is not step:
            raise InvalidDocumentIngestionJob(
                "Only the currently attempted ingestion step can be completed."
            )
        self.last_completed_step = step
        self.current_step_attempt_count = 0
        self.last_attempted_at = None
        self.failure_code = None
        self.failure_message = None
        self._touch(at)

    def increment_retry_count(self, *, at: datetime | None = None) -> None:
        self._require_non_terminal()
        self.retry_count += 1
        self._touch(at)

    def _transition(self, target: IngestionStatus, *, at: datetime | None) -> None:
        self._require_non_terminal()
        allowed = {
            IngestionStatus.queued: {IngestionStatus.running, IngestionStatus.cancelled},
            IngestionStatus.running: {
                IngestionStatus.completed,
                IngestionStatus.failed,
                IngestionStatus.cancelled,
            },
        }
        if target not in allowed.get(self.status, set()):
            raise InvalidDocumentIngestionJob(
                f"Invalid ingestion job transition from {self.status.value} to {target.value}."
            )
        timestamp = self._validated_operation_time(at)
        self.status = target
        if target is IngestionStatus.running and self.started_at is None:
            self.started_at = timestamp
        if target in TERMINAL_STATUSES:
            self.completed_at = timestamp
        self.updated_at = timestamp

    def _touch(self, at: datetime | None) -> None:
        self.updated_at = self._validated_operation_time(at)

    def _validated_operation_time(self, at: datetime | None) -> datetime:
        timestamp = at or utc_now()
        _require_aware(timestamp)
        if timestamp < self.updated_at:
            raise InvalidDocumentIngestionJob("Lifecycle timestamps must be chronological.")
        return timestamp

    def _require_non_terminal(self) -> None:
        if self.status in TERMINAL_STATUSES:
            raise InvalidDocumentIngestionJob("A terminal ingestion job cannot be changed.")

    def _validate_lifecycle(self) -> None:
        if self.status is IngestionStatus.queued:
            if self.started_at is not None or self.completed_at is not None:
                raise InvalidDocumentIngestionJob("A queued job cannot have lifecycle timestamps.")
        elif self.status is IngestionStatus.running:
            if self.started_at is None or self.completed_at is not None:
                raise InvalidDocumentIngestionJob("A running job requires only started_at.")
        elif self.status is IngestionStatus.completed:
            if self.started_at is None or self.completed_at is None:
                raise InvalidDocumentIngestionJob("A completed job requires lifecycle timestamps.")
        elif self.status is IngestionStatus.failed:
            if self.started_at is None or self.completed_at is None:
                raise InvalidDocumentIngestionJob("A failed job requires lifecycle timestamps.")
            if not self.failure_code and not self.failure_message:
                raise InvalidDocumentIngestionJob("A failed job requires failure data.")
        elif self.status is IngestionStatus.cancelled:
            if self.completed_at is None:
                raise InvalidDocumentIngestionJob("A cancelled job requires completed_at.")
        else:
            raise InvalidDocumentIngestionJob(
                f"Unsupported document ingestion status: {self.status}"
            )

        if self.started_at is not None and self.started_at < self.created_at:
            raise InvalidDocumentIngestionJob("started_at cannot precede created_at.")
        if self.completed_at is not None:
            earliest = self.started_at or self.created_at
            if self.completed_at < earliest:
                raise InvalidDocumentIngestionJob("completed_at is not chronological.")
        if self.status not in {IngestionStatus.failed, IngestionStatus.running} and (
            self.failure_code is not None or self.failure_message is not None
        ):
            raise InvalidDocumentIngestionJob(
                "Only a running retry or failed job may contain failure data."
            )
