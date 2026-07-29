import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from time import sleep
from typing import Any, Protocol
from uuid import UUID

from assistant.application.ingestion_retry import (
    FailureCategory,
    FailureClassifier,
    IngestionFailure,
    IngestionFailureClassifier,
    IngestionRetryPolicy,
)
from assistant.domain.content_processing_result import ContentProcessingResult
from assistant.domain.document_ingestion_job import TERMINAL_STATUSES, IngestionStep
from assistant.domain.ingestion_status import IngestionStatus
from assistant.domain.knowledge_persistence import PreparedKnowledge
from assistant.domain.website_document import WebsiteDocument
from assistant.infrastructure.repositories.document_ingestion_job import (
    DocumentIngestionJobRepository,
)
from core.config import IngestionRetrySettings

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
    cause: BaseException | None = field(default=None, repr=False, compare=False)

    @classmethod
    def success(cls) -> "IngestionStepResult":
        return cls(succeeded=True)

    @classmethod
    def failure(
        cls, code: str, message: str, *, cause: BaseException | None = None
    ) -> "IngestionStepResult":
        if not code.strip() or not message.strip():
            raise ValueError("An ingestion step failure requires a safe code and message.")
        return cls(False, code.strip(), message.strip(), cause)


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
    retryable: bool | None = None
    attempts_used: int = 0
    retries_performed: int = 0
    retry_exhausted: bool = False
    total_retries: int = 0


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
        classifier: FailureClassifier | None = None,
        retry_policy: IngestionRetryPolicy | None = None,
        sleeper=sleep,
    ) -> None:
        self._repository = repository
        self._definition = definition
        self._context_factory = context_factory or (
            lambda job_id, document_id, _checkpoint: IngestionPipelineContext(job_id, document_id)
        )
        self._classifier = classifier or IngestionFailureClassifier()
        self._retry_policy = retry_policy or IngestionRetryPolicy(
            IngestionRetrySettings(1, 0, 1, 0, False)
        )
        self._sleeper = sleeper

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
        reconstruction_step = job.last_completed_step
        if job.current_step is not None and job.current_step_attempt_count > 0:
            current_index = REQUIRED_STEP_ORDER.index(job.current_step)
            reconstruction_step = (
                REQUIRED_STEP_ORDER[current_index - 1] if current_index > 0 else None
            )
        try:
            context = self._context_factory(job.id, job.document_id, reconstruction_step)
        except Exception:
            logger.exception(
                "Ingestion context reconstruction failed",
                extra={"job_id": str(job.id), "document_id": job.document_id},
            )
            return self._fail(
                job,
                next_step,
                IngestionFailure(
                    FailureCategory.unexpected,
                    "unexpected_ingestion_error",
                    "Ingestion failed unexpectedly.",
                    False,
                ),
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
            if job.current_step_attempt_count == 0:
                job.begin_step_attempt()
                self._repository.update(job)
            while True:
                attempt_number = job.current_step_attempt_count
                logger.info(
                    "ingestion_step_attempt_started",
                    extra=self._log_fields(job, step.step_id, attempt_number),
                )
                try:
                    outcome = step.execute(context)
                    failure = (
                        None if outcome.succeeded else self._outcome_failure(outcome, step.step_id)
                    )
                except Exception as exc:
                    logger.exception(
                        "ingestion_step_attempt_failed",
                        extra=self._log_fields(job, step.step_id, attempt_number),
                    )
                    failure = self._classifier.classify(exc, step.step_id)
                if failure is None:
                    if attempt_number > 1:
                        logger.info(
                            "ingestion_step_retry_succeeded",
                            extra=self._log_fields(job, step.step_id, attempt_number),
                        )
                    break
                logger.warning(
                    "ingestion_step_attempt_failed",
                    extra=self._log_fields(job, step.step_id, attempt_number, failure),
                )
                if not self._retry_policy.should_retry(failure, attempt_number):
                    exhausted = failure.retryable and (
                        attempt_number >= self._retry_policy.settings.maximum_attempts
                    )
                    logger.error(
                        "ingestion_step_retry_exhausted"
                        if exhausted
                        else "ingestion_step_failed_permanently",
                        extra=self._log_fields(job, step.step_id, attempt_number, failure),
                    )
                    return self._fail(job, step.step_id, failure, retry_exhausted=exhausted)
                retry_number = attempt_number
                delay = self._retry_policy.get_delay(retry_number, failure)
                job = self._repository.record_retry(
                    job.id,
                    step.step_id,
                    failure.failure_code,
                    failure.failure_message,
                )
                logger.info(
                    "ingestion_step_retry_scheduled",
                    extra={
                        **self._log_fields(
                            job, step.step_id, job.current_step_attempt_count, failure
                        ),
                        "delay_seconds": delay,
                    },
                )
                self._sleeper(delay)
                logger.info(
                    "ingestion_step_retry_started",
                    extra=self._log_fields(job, step.step_id, job.current_step_attempt_count),
                )
            if step.step_id in self._definition.checkpoint_steps:
                job.mark_step_completed(step.step_id)
                self._repository.update(job)
            else:
                job.current_step_attempt_count = 0
                job.last_attempted_at = None
                job.failure_code = None
                job.failure_message = None
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
            retries_performed=job.retry_count,
            total_retries=job.retry_count,
        )

    def _fail(
        self,
        job: Any,
        step: IngestionStep,
        failure: IngestionFailure,
        *,
        retry_exhausted: bool = False,
    ) -> IngestionPipelineResult:
        job.mark_failed(failure.failure_code, failure.failure_message)
        self._repository.update(job)
        logger.error(
            "pipeline_failed",
            extra={
                "job_id": str(job.id),
                "step": step.value,
                "failure_code": failure.failure_code,
            },
        )
        return IngestionPipelineResult(
            job.id,
            job.status,
            False,
            last_completed_step=job.last_completed_step,
            failed_step=step,
            failure_code=failure.failure_code,
            failure_message=failure.failure_message,
            retryable=failure.retryable,
            attempts_used=job.current_step_attempt_count,
            retries_performed=max(0, job.current_step_attempt_count - 1),
            retry_exhausted=retry_exhausted,
            total_retries=job.retry_count,
        )

    def _outcome_failure(
        self, outcome: IngestionStepResult, step: IngestionStep
    ) -> IngestionFailure:
        if outcome.cause is not None:
            return self._classifier.classify(outcome.cause, step)
        return IngestionFailure(
            FailureCategory.validation,
            outcome.failure_code or "ingestion_step_failed",
            outcome.failure_message or "Ingestion step failed.",
            False,
        )

    def _log_fields(
        self,
        job: Any,
        step: IngestionStep,
        attempt_number: int,
        failure: IngestionFailure | None = None,
    ) -> dict[str, object]:
        fields: dict[str, object] = {
            "job_id": str(job.id),
            "document_id": job.document_id,
            "step": step.value,
            "attempt_number": attempt_number,
            "maximum_attempts": self._retry_policy.settings.maximum_attempts,
        }
        if failure is not None:
            fields.update(
                failure_code=failure.failure_code,
                retryable=failure.retryable,
            )
        return fields

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
