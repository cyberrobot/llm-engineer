from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest

from assistant.application.ingestion_pipeline import (
    IngestionPipelineContext,
    IngestionPipelineDefinition,
    IngestionPipelineRunner,
    IngestionStepResult,
    InvalidIngestionPipeline,
)
from assistant.domain.document_ingestion_job import DocumentIngestionJob, IngestionStep
from assistant.domain.ingestion_status import IngestionStatus
from assistant.infrastructure.repositories.document_ingestion_job import (
    InMemoryDocumentIngestionJobRepository,
)


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
    assert "provider token secret" in caplog.text


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
