from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import psycopg
import pytest

from assistant.application.ingestion_pipeline import (
    IngestionPipelineContext,
    IngestionPipelineDefinition,
    IngestionPipelineRunner,
    IngestionStepResult,
    InvalidIngestionPipeline,
)
from assistant.application.ingestion_retry import (
    IngestionFailureClassifier,
    IngestionRetryPolicy,
)
from assistant.domain.document_ingestion_job import DocumentIngestionJob, IngestionStep
from assistant.domain.ingestion_status import IngestionStatus
from assistant.infrastructure.repositories.document_ingestion_job import (
    InMemoryDocumentIngestionJobRepository,
)
from assistant.infrastructure.repositories.ingestion_observability import (
    InMemoryIngestionStepExecutionRepository,
)
from core.config import IngestionRetrySettings
from infrastructure.ai.exceptions import AIRateLimitError, AITimeoutError


@dataclass
class FakeStep:
    step_id: IngestionStep
    calls: list[IngestionStep]
    result: IngestionStepResult = IngestionStepResult.success()
    error: Exception | None = None

    def execute(self, context: IngestionPipelineContext) -> IngestionStepResult:
        assert context.job_id
        self.calls.append(self.step_id)
        if self.error is not None:
            raise self.error
        return self.result


@dataclass
class SequencedStep:
    step_id: IngestionStep
    calls: list[IngestionStep]
    outcomes: list[IngestionStepResult | Exception]

    def execute(self, context: IngestionPipelineContext) -> IngestionStepResult:
        self.calls.append(self.step_id)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class RecordingSleeper:
    def __init__(self) -> None:
        self.delays: list[float] = []

    def __call__(self, delay: float) -> None:
        self.delays.append(delay)


class RecordingRepository(InMemoryDocumentIngestionJobRepository):
    def __init__(self, document_id: str) -> None:
        super().__init__(document_ids={document_id})
        self.snapshots: list[DocumentIngestionJob] = []

    def update(self, job: DocumentIngestionJob) -> None:
        super().update(job)
        stored = self.get_by_id(job.id)
        assert stored is not None
        self.snapshots.append(stored)


def pipeline(calls: list[IngestionStep], **overrides: FakeStep) -> IngestionPipelineDefinition:
    steps = [
        overrides.get(step.value, FakeStep(step, calls))
        for step in (
            IngestionStep.parse,
            IngestionStep.chunk,
            IngestionStep.embed,
            IngestionStep.persist,
        )
    ]
    return IngestionPipelineDefinition(steps)


def stored_job(repository: RecordingRepository, job_id: UUID) -> DocumentIngestionJob:
    job = repository.get_by_id(job_id)
    assert job is not None
    return job


def test_pipeline_definition_requires_each_step_once_in_explicit_order():
    calls: list[IngestionStep] = []
    definition = pipeline(calls)

    assert [step.step_id for step in definition.steps] == list(IngestionStep)
    coarse = IngestionPipelineDefinition(
        definition.steps, checkpoint_steps=(IngestionStep.persist,)
    )
    assert coarse.checkpoint_steps == {IngestionStep.persist}

    with pytest.raises(InvalidIngestionPipeline, match="duplicate"):
        IngestionPipelineDefinition(
            [FakeStep(IngestionStep.parse, calls), FakeStep(IngestionStep.parse, calls)]
        )
    with pytest.raises(InvalidIngestionPipeline, match="missing"):
        IngestionPipelineDefinition([FakeStep(IngestionStep.parse, calls)])
    with pytest.raises(InvalidIngestionPipeline, match="order"):
        IngestionPipelineDefinition(
            [
                FakeStep(IngestionStep.chunk, calls),
                FakeStep(IngestionStep.parse, calls),
                FakeStep(IngestionStep.embed, calls),
                FakeStep(IngestionStep.persist, calls),
            ]
        )
    with pytest.raises(InvalidIngestionPipeline, match="must be checkpointed"):
        IngestionPipelineDefinition(definition.steps, checkpoint_steps=(IngestionStep.parse,))


def test_runner_executes_in_order_commits_each_checkpoint_and_completes():
    document_id = str(uuid4())
    repository = RecordingRepository(document_id)
    created = repository.create(DocumentIngestionJob.create(document_id))
    calls: list[IngestionStep] = []

    result = IngestionPipelineRunner(repository, pipeline(calls)).run(created.id)

    assert result.succeeded
    assert result.status is IngestionStatus.completed
    assert result.last_completed_step is IngestionStep.persist
    assert calls == list(IngestionStep)
    checkpoints = [
        snapshot.last_completed_step
        for snapshot in repository.snapshots
        if snapshot.last_completed_step is not None
        and snapshot.current_step is snapshot.last_completed_step
    ]
    assert checkpoints == [
        IngestionStep.parse,
        IngestionStep.chunk,
        IngestionStep.embed,
        IngestionStep.persist,
    ]
    completed = stored_job(repository, created.id)
    assert completed.current_step is None
    assert completed.started_at is not None
    assert completed.completed_at is not None


def test_new_runner_resumes_after_checkpoint_without_reexecuting_completed_steps():
    document_id = str(uuid4())
    repository = RecordingRepository(document_id)
    created = DocumentIngestionJob.create(document_id)
    created.mark_running()
    created.set_current_step(IngestionStep.parse)
    created.mark_step_completed(IngestionStep.parse)
    repository.create(created)
    started_at = created.started_at
    calls: list[IngestionStep] = []

    result = IngestionPipelineRunner(repository, pipeline(calls)).run(created.id)

    assert result.succeeded
    assert calls == [IngestionStep.chunk, IngestionStep.embed, IngestionStep.persist]
    assert stored_job(repository, created.id).started_at == started_at


def test_failure_stops_later_steps_does_not_checkpoint_failure_and_persists_safe_details():
    document_id = str(uuid4())
    repository = RecordingRepository(document_id)
    created = repository.create(DocumentIngestionJob.create(document_id))
    calls: list[IngestionStep] = []
    failed = FakeStep(
        IngestionStep.chunk,
        calls,
        IngestionStepResult.failure("invalid_content", "Document content is invalid."),
    )

    result = IngestionPipelineRunner(repository, pipeline(calls, chunk=failed)).run(created.id)

    assert not result.succeeded
    assert result.failed_step is IngestionStep.chunk
    assert result.failure_code == "invalid_content"
    assert calls == [IngestionStep.parse, IngestionStep.chunk]
    stored = stored_job(repository, created.id)
    assert stored.status is IngestionStatus.failed
    assert stored.last_completed_step is IngestionStep.parse
    assert stored.failure_message == "Document content is invalid."


def test_unexpected_exception_becomes_safe_typed_failure_without_leaking_details(caplog):
    document_id = str(uuid4())
    repository = RecordingRepository(document_id)
    created = repository.create(DocumentIngestionJob.create(document_id))
    calls: list[IngestionStep] = []
    exploding = FakeStep(IngestionStep.parse, calls, error=RuntimeError("provider token secret"))

    result = IngestionPipelineRunner(repository, pipeline(calls, parse=exploding)).run(created.id)

    assert result.failure_code == "unexpected_ingestion_error"
    assert result.failure_message == "Ingestion failed unexpectedly."
    assert "provider token secret" not in result.failure_message
    stored = stored_job(repository, created.id)
    assert stored.status is IngestionStatus.failed
    assert stored.last_completed_step is None
    assert "provider token secret" not in (stored.failure_message or "")
    assert "provider token secret" not in caplog.text


@pytest.mark.parametrize("terminal", ["completed", "failed", "cancelled"])
def test_terminal_jobs_are_not_executed(terminal: str):
    document_id = str(uuid4())
    repository = RecordingRepository(document_id)
    job = DocumentIngestionJob.create(document_id)
    job.mark_running()
    if terminal == "completed":
        for step in IngestionStep:
            job.set_current_step(step)
            job.mark_step_completed(step)
        job.mark_completed()
    elif terminal == "failed":
        job.mark_failed("ingestion_step_failed", "Failed safely.")
    else:
        job.mark_cancelled()
    repository.create(job)
    calls: list[IngestionStep] = []

    result = IngestionPipelineRunner(repository, pipeline(calls)).run(job.id)

    assert not result.succeeded
    assert result.failure_code == "ingestion_job_not_runnable"
    assert calls == []


def test_inconsistent_completed_checkpoint_is_rejected_without_execution():
    document_id = str(uuid4())
    repository = RecordingRepository(document_id)
    job = DocumentIngestionJob.create(document_id)
    job.mark_running()
    job.set_current_step(IngestionStep.chunk)
    job.mark_step_completed(IngestionStep.chunk)
    job.mark_completed()
    repository.create(job)
    calls: list[IngestionStep] = []

    result = IngestionPipelineRunner(repository, pipeline(calls)).run(job.id)

    assert result.failure_code == "invalid_ingestion_job_checkpoint"
    assert calls == []


def test_unknown_job_returns_typed_not_found_result():
    document_id = str(uuid4())
    result = IngestionPipelineRunner(RecordingRepository(document_id), pipeline([])).run(uuid4())

    assert result.failure_code == "ingestion_job_not_found"
    assert result.status is None


def test_retryable_failure_retries_only_same_step_and_persists_count_before_sleep():
    document_id = str(uuid4())
    repository = RecordingRepository(document_id)
    created = repository.create(DocumentIngestionJob.create(document_id))
    calls: list[IngestionStep] = []
    embed = SequencedStep(
        IngestionStep.embed,
        calls,
        [AITimeoutError(), IngestionStepResult.success()],
    )
    sleeper = RecordingSleeper()
    definition = pipeline(calls, embed=embed)  # type: ignore[arg-type]
    runner = IngestionPipelineRunner(
        repository,
        definition,
        classifier=IngestionFailureClassifier(),
        retry_policy=IngestionRetryPolicy(IngestionRetrySettings(3, 1, 2, 30, False)),
        sleeper=sleeper,
    )

    result = runner.run(created.id)

    assert result.succeeded
    assert calls == [
        IngestionStep.parse,
        IngestionStep.chunk,
        IngestionStep.embed,
        IngestionStep.embed,
        IngestionStep.persist,
    ]
    assert sleeper.delays == [1]
    assert result.total_retries == 1
    stored = stored_job(repository, created.id)
    assert stored.retry_count == 1
    assert stored.current_step_attempt_count == 0
    assert stored.failure_code is None
    retry_snapshot = next(
        snapshot for snapshot in repository.snapshots if snapshot.retry_count == 1
    )
    assert retry_snapshot.status is IngestionStatus.running
    assert retry_snapshot.current_step is IngestionStep.embed
    assert retry_snapshot.current_step_attempt_count == 2


def test_non_retryable_failure_fails_without_sleep_or_retry_increment():
    document_id = str(uuid4())
    repository = RecordingRepository(document_id)
    created = repository.create(DocumentIngestionJob.create(document_id))
    calls: list[IngestionStep] = []
    sleeper = RecordingSleeper()
    parse = SequencedStep(IngestionStep.parse, calls, [ValueError("invalid input")])

    result = IngestionPipelineRunner(
        repository,
        pipeline(calls, parse=parse),
        sleeper=sleeper,  # type: ignore[arg-type]
    ).run(created.id)

    assert not result.succeeded
    assert not result.retryable
    assert not result.retry_exhausted
    assert result.attempts_used == 1
    assert sleeper.delays == []
    assert stored_job(repository, created.id).retry_count == 0


def test_retry_exhaustion_fails_safely_without_advancing_or_running_later_steps():
    document_id = str(uuid4())
    repository = RecordingRepository(document_id)
    created = repository.create(DocumentIngestionJob.create(document_id))
    calls: list[IngestionStep] = []
    sleeper = RecordingSleeper()
    parse = SequencedStep(
        IngestionStep.parse,
        calls,
        [AIRateLimitError(), AIRateLimitError(), AIRateLimitError()],
    )
    result = IngestionPipelineRunner(
        repository,
        pipeline(calls, parse=parse),  # type: ignore[arg-type]
        classifier=IngestionFailureClassifier(),
        retry_policy=IngestionRetryPolicy(IngestionRetrySettings(3, 1, 2, 30, False)),
        sleeper=sleeper,
    ).run(created.id)

    assert not result.succeeded
    assert result.retryable
    assert result.retry_exhausted
    assert result.attempts_used == 3
    assert result.retries_performed == 2
    assert calls == [IngestionStep.parse] * 3
    assert sleeper.delays == [1, 2]
    stored = stored_job(repository, created.id)
    assert stored.status is IngestionStatus.failed
    assert stored.last_completed_step is None
    assert stored.retry_count == 2
    assert stored.failure_code == "ingestion_rate_limited"


def test_pipeline_persists_step_attempt_timing_and_retry_history():
    document_id = str(uuid4())
    repository = RecordingRepository(document_id)
    created = repository.create(DocumentIngestionJob.create(document_id))
    executions = InMemoryIngestionStepExecutionRepository()
    calls: list[IngestionStep] = []
    embed = SequencedStep(
        IngestionStep.embed,
        calls,
        [AITimeoutError(), IngestionStepResult.success()],
    )
    wall_times = iter(
        datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc) + timedelta(seconds=value)
        for value in range(20)
    )
    monotonic_times = iter(float(value) for value in range(20))
    runner = IngestionPipelineRunner(
        repository,
        pipeline(calls, embed=embed),  # type: ignore[arg-type]
        classifier=IngestionFailureClassifier(),
        retry_policy=IngestionRetryPolicy(IngestionRetrySettings(2, 0, 1, 0, False)),
        sleeper=lambda _delay: None,
        step_executions=executions,
        now=lambda: next(wall_times),
        monotonic_clock=lambda: next(monotonic_times),
    )

    result = runner.run(created.id)

    assert result.succeeded
    history = executions.list_for_job(created.id)
    assert [(item.step, item.attempt_number, item.status.value) for item in history] == [
        (IngestionStep.parse, 1, "completed"),
        (IngestionStep.chunk, 1, "completed"),
        (IngestionStep.embed, 1, "failed"),
        (IngestionStep.embed, 2, "completed"),
        (IngestionStep.persist, 1, "completed"),
    ]
    assert all(item.duration_ms == 1_000 for item in history)
    assert history[2].failure_code == "ingestion_timeout"
    assert history[2].retryable is True


def test_metrics_exporter_failure_does_not_change_successful_ingestion():
    class FailingMetrics:
        def __getattr__(self, _name):
            def fail(*_args, **_kwargs):
                raise RuntimeError("metrics backend unavailable")

            return fail

    document_id = str(uuid4())
    repository = RecordingRepository(document_id)
    created = repository.create(DocumentIngestionJob.create(document_id))

    result = IngestionPipelineRunner(
        repository,
        pipeline([]),
        metrics=FailingMetrics(),  # type: ignore[arg-type]
    ).run(created.id)

    assert result.succeeded
    assert stored_job(repository, created.id).status is IngestionStatus.completed


def test_new_runner_retains_scheduled_attempt_and_completed_checkpoint_after_interruption():
    document_id = str(uuid4())
    repository = RecordingRepository(document_id)
    job = DocumentIngestionJob.create(document_id)
    job.mark_running()
    job.set_current_step(IngestionStep.parse)
    job.begin_step_attempt()
    job.mark_step_completed(IngestionStep.parse)
    job.set_current_step(IngestionStep.chunk)
    job.begin_step_attempt()
    job.mark_step_completed(IngestionStep.chunk)
    job.set_current_step(IngestionStep.embed)
    job.begin_step_attempt()
    job.schedule_retry("ingestion_timeout", "The ingestion operation timed out.")
    repository.create(job)
    calls: list[IngestionStep] = []
    embed = SequencedStep(IngestionStep.embed, calls, [IngestionStepResult.success()])

    result = IngestionPipelineRunner(
        repository,
        pipeline(calls, embed=embed),  # type: ignore[arg-type]
        classifier=IngestionFailureClassifier(),
        retry_policy=IngestionRetryPolicy(IngestionRetrySettings(3, 0, 2, 30, False)),
        sleeper=RecordingSleeper(),
    ).run(job.id)

    assert result.succeeded
    assert calls == [IngestionStep.embed, IngestionStep.persist]
    assert stored_job(repository, job.id).retry_count == 1


def test_restart_at_final_scheduled_attempt_does_not_grant_an_extra_retry():
    document_id = str(uuid4())
    repository = RecordingRepository(document_id)
    job = DocumentIngestionJob.create(document_id)
    job.mark_running()
    job.set_current_step(IngestionStep.parse)
    job.begin_step_attempt()
    job.schedule_retry("ingestion_rate_limited", "Provider rate limited.")
    job.schedule_retry("ingestion_rate_limited", "Provider rate limited.")
    repository.create(job)
    calls: list[IngestionStep] = []
    parse = SequencedStep(IngestionStep.parse, calls, [AIRateLimitError()])
    sleeper = RecordingSleeper()

    result = IngestionPipelineRunner(
        repository,
        pipeline(calls, parse=parse),  # type: ignore[arg-type]
        classifier=IngestionFailureClassifier(),
        retry_policy=IngestionRetryPolicy(IngestionRetrySettings(3, 0, 2, 30, False)),
        sleeper=sleeper,
    ).run(job.id)

    assert not result.succeeded
    assert result.retry_exhausted
    assert calls == [IngestionStep.parse]
    assert sleeper.delays == []
    assert stored_job(repository, job.id).retry_count == 2


def test_transient_database_failure_retries_persist_without_restarting_prior_steps():
    document_id = str(uuid4())
    repository = RecordingRepository(document_id)
    created = repository.create(DocumentIngestionJob.create(document_id))
    calls: list[IngestionStep] = []
    persist = SequencedStep(
        IngestionStep.persist,
        calls,
        [psycopg.OperationalError("private database detail"), IngestionStepResult.success()],
    )

    result = IngestionPipelineRunner(
        repository,
        pipeline(calls, persist=persist),  # type: ignore[arg-type]
        classifier=IngestionFailureClassifier(),
        retry_policy=IngestionRetryPolicy(IngestionRetrySettings(3, 0, 2, 30, False)),
        sleeper=RecordingSleeper(),
    ).run(created.id)

    assert result.succeeded
    assert calls == [
        IngestionStep.parse,
        IngestionStep.chunk,
        IngestionStep.embed,
        IngestionStep.persist,
        IngestionStep.persist,
    ]
    assert stored_job(repository, created.id).retry_count == 1
