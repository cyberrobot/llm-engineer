import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import UUID

from assistant.domain.content_processing_result import ContentProcessingResult
from assistant.domain.document_ingestion_job import TERMINAL_STATUSES, IngestionStep
from assistant.domain.ingestion_status import IngestionStatus
from assistant.domain.knowledge_persistence import PreparedKnowledge
from assistant.domain.website_document import WebsiteDocument
from assistant.infrastructure.repositories.document_ingestion_job import (
    DocumentIngestionJobRepository,
)

logger = logging.getLogger(__name__)

REQUIRED_STEP_ORDER = tuple(IngestionStep)


class InvalidIngestionPipeline(ValueError):
    pass


@dataclass
class IngestionPipelineContext:
    job_id: UUID
    document_id: str
    parsed_document: Sequence[WebsiteDocument] | None = None
    chunks: ContentProcessingResult | None = None
    embeddings: PreparedKnowledge | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class IngestionStepResult:
    succeeded: bool
    failure_code: str | None = None
    failure_message: str | None = None

    @classmethod
    def success(cls) -> "IngestionStepResult":
        return cls(succeeded=True)

    @classmethod
    def failure(cls, code: str, message: str) -> "IngestionStepResult":
        if not code.strip() or not message.strip():
            raise ValueError("An ingestion step failure requires a safe code and message.")
        return cls(False, code.strip(), message.strip())


class IngestionPipelineStep(Protocol):
    @property
    def step_id(self) -> IngestionStep: ...

    def execute(self, context: IngestionPipelineContext) -> IngestionStepResult: ...


class IngestionContextFactory(Protocol):
    def __call__(
        self,
        job_id: UUID,
        document_id: str,
        last_completed_step: IngestionStep | None,
    ) -> IngestionPipelineContext: ...


@dataclass(frozen=True)
class IngestionPipelineResult:
    job_id: UUID
    status: IngestionStatus | None
    succeeded: bool
    last_completed_step: IngestionStep | None = None
    failed_step: IngestionStep | None = None
    failure_code: str | None = None
    failure_message: str | None = None


class IngestionPipelineDefinition:
    def __init__(
        self,
        steps: Sequence[IngestionPipelineStep],
        *,
        checkpoint_steps: Sequence[IngestionStep] = REQUIRED_STEP_ORDER,
    ) -> None:
        identities = tuple(step.step_id for step in steps)
        if len(identities) != len(set(identities)):
            raise InvalidIngestionPipeline("The ingestion pipeline contains duplicate steps.")
        missing = [step.value for step in REQUIRED_STEP_ORDER if step not in identities]
        if missing:
            raise InvalidIngestionPipeline(
                f"The ingestion pipeline is missing required steps: {', '.join(missing)}."
            )
        if identities != REQUIRED_STEP_ORDER:
            raise InvalidIngestionPipeline("The ingestion pipeline steps are in an invalid order.")
        checkpoint_identities = tuple(checkpoint_steps)
        if len(checkpoint_identities) != len(set(checkpoint_identities)):
            raise InvalidIngestionPipeline("The ingestion pipeline contains duplicate checkpoints.")
        if IngestionStep.persist not in checkpoint_identities:
            raise InvalidIngestionPipeline("The final persistence step must be checkpointed.")
        if any(step not in identities for step in checkpoint_identities):
            raise InvalidIngestionPipeline("The ingestion pipeline has an unknown checkpoint.")
        self._steps = tuple(steps)
        self._checkpoint_steps = frozenset(checkpoint_identities)

    @property
    def steps(self) -> tuple[IngestionPipelineStep, ...]:
        return self._steps

    @property
    def checkpoint_steps(self) -> frozenset[IngestionStep]:
        return self._checkpoint_steps


class IngestionPipelineRunner:
    def __init__(
        self,
        repository: DocumentIngestionJobRepository,
        definition: IngestionPipelineDefinition,
        *,
        context_factory: IngestionContextFactory | None = None,
    ) -> None:
        self._repository = repository
        self._definition = definition
        self._context_factory = context_factory or (
            lambda job_id, document_id, _checkpoint: IngestionPipelineContext(job_id, document_id)
        )

    def run(self, job_id: UUID) -> IngestionPipelineResult:
        job = self._repository.get_by_id(job_id)
        if job is None:
            return IngestionPipelineResult(
                job_id,
                None,
                False,
                failure_code="ingestion_job_not_found",
                failure_message="Ingestion job not found.",
            )
        consistency_error = self._checkpoint_error(job.status, job.last_completed_step)
        if consistency_error is not None:
            logger.error(
                "Ingestion pipeline checkpoint is inconsistent",
                extra={
                    "job_id": str(job.id),
                    "document_id": job.document_id,
                    "status": job.status.value,
                    "last_completed_step": (
                        job.last_completed_step.value if job.last_completed_step else None
                    ),
                },
            )
            return self._rejected(job, "invalid_ingestion_job_checkpoint", consistency_error)
        if job.status in TERMINAL_STATUSES:
            return self._rejected(
                job,
                "ingestion_job_not_runnable",
                "A terminal ingestion job cannot be executed.",
            )

        if job.status is IngestionStatus.queued:
            job.mark_running()
            self._repository.update(job)
        next_step = self._next_step(job.last_completed_step)
        try:
            context = self._context_factory(job.id, job.document_id, job.last_completed_step)
        except Exception:
            logger.exception(
                "Ingestion context reconstruction failed",
                extra={"job_id": str(job.id), "document_id": job.document_id},
            )
            return self._fail(
                job,
                next_step,
                "unexpected_ingestion_error",
                "Ingestion failed unexpectedly.",
            )
        logger.info(
            "pipeline_started",
            extra={"job_id": str(job.id), "document_id": job.document_id},
        )

        completed_index = (
            REQUIRED_STEP_ORDER.index(job.last_completed_step)
            if job.last_completed_step is not None
            else -1
        )
        for index, step in enumerate(self._definition.steps):
            if index <= completed_index:
                logger.info(
                    "step_skipped",
                    extra={"job_id": str(job.id), "step": step.step_id.value},
                )
                continue
            job.set_current_step(step.step_id)
            self._repository.update(job)
            logger.info(
                "step_started",
                extra={"job_id": str(job.id), "step": step.step_id.value},
            )
            try:
                outcome = step.execute(context)
            except Exception:
                logger.exception(
                    "step_failed",
                    extra={"job_id": str(job.id), "step": step.step_id.value},
                )
                return self._fail(
                    job,
                    step.step_id,
                    "unexpected_ingestion_error",
                    "Ingestion failed unexpectedly.",
                )
            if not outcome.succeeded:
                logger.warning(
                    "step_failed",
                    extra={
                        "job_id": str(job.id),
                        "step": step.step_id.value,
                        "failure_code": outcome.failure_code,
                    },
                )
                return self._fail(
                    job,
                    step.step_id,
                    outcome.failure_code or "ingestion_step_failed",
                    outcome.failure_message or "Ingestion step failed.",
                )
            if step.step_id in self._definition.checkpoint_steps:
                job.mark_step_completed(step.step_id)
                self._repository.update(job)
            logger.info(
                "step_completed",
                extra={"job_id": str(job.id), "step": step.step_id.value},
            )

        job.mark_completed()
        self._repository.update(job)
        logger.info(
            "pipeline_completed",
            extra={"job_id": str(job.id), "document_id": job.document_id},
        )
        return IngestionPipelineResult(
            job.id,
            job.status,
            True,
            last_completed_step=job.last_completed_step,
        )

    def _fail(
        self,
        job: Any,
        step: IngestionStep,
        code: str,
        message: str,
    ) -> IngestionPipelineResult:
        job.mark_failed(code, message)
        self._repository.update(job)
        logger.error(
            "pipeline_failed",
            extra={"job_id": str(job.id), "step": step.value, "failure_code": code},
        )
        return IngestionPipelineResult(
            job.id,
            job.status,
            False,
            last_completed_step=job.last_completed_step,
            failed_step=step,
            failure_code=code,
            failure_message=message,
        )

    @staticmethod
    def _checkpoint_error(status: IngestionStatus, checkpoint: IngestionStep | None) -> str | None:
        if status is IngestionStatus.completed and checkpoint is not IngestionStep.persist:
            return "Completed ingestion job does not have the final checkpoint."
        if status is IngestionStatus.queued and checkpoint is not None:
            return "Queued ingestion job cannot have a completed checkpoint."
        return None

    @staticmethod
    def _next_step(checkpoint: IngestionStep | None) -> IngestionStep:
        if checkpoint is None:
            return IngestionStep.parse
        index = REQUIRED_STEP_ORDER.index(checkpoint)
        return REQUIRED_STEP_ORDER[min(index + 1, len(REQUIRED_STEP_ORDER) - 1)]

    @staticmethod
    def _rejected(job: Any, code: str, message: str) -> IngestionPipelineResult:
        return IngestionPipelineResult(
            job.id,
            job.status,
            False,
            last_completed_step=job.last_completed_step,
            failure_code=code,
            failure_message=message,
        )
