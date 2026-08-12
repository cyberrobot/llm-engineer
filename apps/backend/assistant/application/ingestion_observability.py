from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone

from assistant.domain.document_ingestion_job import DocumentIngestionJob, IngestionStep
from assistant.domain.ingestion_status import IngestionStatus


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class IngestionProgress:
    current_step: IngestionStep | None
    last_completed_step: IngestionStep | None
    completed_step_count: int
    total_step_count: int
    progress_percent: int
    current_step_attempt_count: int
    queued_at: datetime
    queue_wait_duration_ms: int | None
    processing_duration_ms: int | None
    total_duration_ms: int


class IngestionProgressCalculator:
    """Derive user-visible progress exclusively from the durable job snapshot."""

    def __init__(
        self,
        ordered_steps: Sequence[IngestionStep],
        *,
        now: Callable[[], datetime] = utc_now,
    ) -> None:
        self._steps = tuple(ordered_steps)
        if not self._steps:
            raise ValueError("Ingestion progress requires at least one step.")
        if len(self._steps) != len(set(self._steps)):
            raise ValueError("Ingestion progress steps must be unique.")
        self._now = now

    def calculate(
        self, job: DocumentIngestionJob, *, at: datetime | None = None
    ) -> IngestionProgress:
        observed_at = at or self._now()
        completed = self._completed_count(job)
        total = len(self._steps)
        progress_percent = min(100, max(0, round(completed / total * 100)))
        if job.status is IngestionStatus.completed:
            completed = total
            progress_percent = 100

        processing_end = job.completed_at or observed_at
        total_end = job.completed_at or observed_at
        return IngestionProgress(
            current_step=job.current_step,
            last_completed_step=job.last_completed_step,
            completed_step_count=completed,
            total_step_count=total,
            progress_percent=progress_percent,
            current_step_attempt_count=job.current_step_attempt_count,
            queued_at=job.created_at,
            queue_wait_duration_ms=(
                self._duration_ms(job.created_at, job.started_at)
                if job.started_at is not None
                else None
            ),
            processing_duration_ms=(
                self._duration_ms(job.started_at, processing_end)
                if job.started_at is not None
                else None
            ),
            total_duration_ms=self._duration_ms(job.created_at, total_end),
        )

    def _completed_count(self, job: DocumentIngestionJob) -> int:
        if job.last_completed_step is None:
            return 0
        try:
            return self._steps.index(job.last_completed_step) + 1
        except ValueError:
            return 0

    @staticmethod
    def _duration_ms(start: datetime, end: datetime) -> int:
        return max(0, round((end - start).total_seconds() * 1_000))


@dataclass(frozen=True)
class IngestionOperationalStatus:
    queued_jobs: int
    running_jobs: int
    recoverable_jobs: int
    oldest_queued_age_seconds: float
    workers_observed: int
    failed_jobs: int = 0
