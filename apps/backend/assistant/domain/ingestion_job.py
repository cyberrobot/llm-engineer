from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4

from assistant.domain.ingestion_status import IngestionStatus


class InvalidIngestionJob(ValueError):
    """Raised when an ingestion job violates its lifecycle invariants."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _require_aware(timestamp: datetime) -> None:
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise InvalidIngestionJob("Ingestion job timestamps must be timezone-aware.")


@dataclass
class IngestionJob:
    id: UUID
    source_url: str
    status: IngestionStatus
    documents_discovered: int
    documents_processed: int
    chunks_created: int
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None

    def __post_init__(self) -> None:
        if not self.source_url.strip():
            raise InvalidIngestionJob("An ingestion job requires a source URL.")
        for timestamp in (self.created_at, self.started_at, self.completed_at):
            if timestamp is not None:
                _require_aware(timestamp)
        self._validate_counts(
            self.documents_discovered,
            self.documents_processed,
            self.chunks_created,
        )
        self._validate_persisted_lifecycle()

    @classmethod
    def create(
        cls,
        source_url: str,
        *,
        job_id: UUID | None = None,
        created_at: datetime | None = None,
    ) -> "IngestionJob":
        return cls(
            id=job_id or uuid4(),
            source_url=source_url,
            status=IngestionStatus.pending,
            documents_discovered=0,
            documents_processed=0,
            chunks_created=0,
            error_message=None,
            created_at=created_at or _utc_now(),
            started_at=None,
            completed_at=None,
        )

    def start(self, *, at: datetime | None = None) -> None:
        if self.status is not IngestionStatus.pending:
            raise InvalidIngestionJob(f"Cannot restart a {self.status.value} job.")
        started_at = at or _utc_now()
        self._require_transition_time(started_at, self.created_at)
        self.status = IngestionStatus.running
        self.started_at = started_at

    def complete(
        self,
        *,
        documents_discovered: int,
        documents_processed: int,
        chunks_created: int,
        at: datetime | None = None,
    ) -> None:
        if self.status is not IngestionStatus.running:
            raise InvalidIngestionJob("Only a running job can be completed.")
        self._validate_counts(documents_discovered, documents_processed, chunks_created)
        completed_at = at or _utc_now()
        if self.started_at is None:
            raise InvalidIngestionJob("A completed job requires a start timestamp.")
        self._require_transition_time(completed_at, self.started_at)

        self.documents_discovered = documents_discovered
        self.documents_processed = documents_processed
        self.chunks_created = chunks_created
        self.error_message = None
        self.status = IngestionStatus.completed
        self.completed_at = completed_at

    def fail(self, error_message: str, *, at: datetime | None = None) -> None:
        if self.status in (IngestionStatus.completed, IngestionStatus.failed):
            raise InvalidIngestionJob(f"Cannot fail a {self.status.value} job.")
        message = error_message.strip()
        if not message:
            raise InvalidIngestionJob("A failed job requires an error message.")
        failed_at = at or _utc_now()
        self._require_transition_time(failed_at, self.started_at or self.created_at)

        self.status = IngestionStatus.failed
        self.error_message = message
        self.completed_at = failed_at

    @staticmethod
    def _validate_counts(discovered: int, processed: int, chunks: int) -> None:
        if min(discovered, processed, chunks) < 0 or processed > discovered:
            raise InvalidIngestionJob("Ingestion job counts are inconsistent.")

    @staticmethod
    def _require_transition_time(timestamp: datetime, earliest: datetime) -> None:
        _require_aware(timestamp)
        if timestamp < earliest:
            raise InvalidIngestionJob("Lifecycle timestamps must be chronological.")

    def _validate_persisted_lifecycle(self) -> None:
        if self.started_at is not None:
            self._require_transition_time(self.started_at, self.created_at)
        if self.completed_at is not None:
            self._require_transition_time(self.completed_at, self.started_at or self.created_at)

        if self.status is IngestionStatus.pending:
            if self.started_at is not None or self.completed_at is not None:
                raise InvalidIngestionJob("A pending job cannot have lifecycle timestamps.")
        elif self.status is IngestionStatus.running:
            if self.started_at is None or self.completed_at is not None:
                raise InvalidIngestionJob("A running job requires only a start timestamp.")
        elif self.status is IngestionStatus.completed:
            if self.started_at is None or self.completed_at is None:
                raise InvalidIngestionJob(
                    "A completed job requires start and completion timestamps."
                )
        elif self.completed_at is None:
            raise InvalidIngestionJob("A failed job requires a completion timestamp.")

        if self.status is IngestionStatus.failed:
            if self.error_message is None or not self.error_message.strip():
                raise InvalidIngestionJob("A failed job requires an error message.")
        elif self.error_message is not None:
            raise InvalidIngestionJob("Only a failed job may have an error message.")
