"""Synchronous application-level orchestration for in-memory evaluation runs."""

from collections.abc import Callable, Sequence
from copy import deepcopy
from datetime import datetime, timezone
from typing import Protocol
from uuid import uuid4

from pydantic import ConfigDict, Field, JsonValue, StrictBool

from assistant.domain import KnowledgeChunk
from assistant.evaluation.answer_adapter import evaluate_chat_response
from assistant.evaluation.answer_evaluator import summarise_answer_results
from assistant.evaluation.models import (
    AnswerEvaluationOptions,
    AnswerEvaluationResult,
    EvaluationCase,
    EvaluationCaseResult,
    EvaluationCaseStatus,
    EvaluationDataset,
    EvaluationRun,
    EvaluationRunStatus,
    EvaluationSummary,
    PositiveInt,
    RetrievalEvaluationResult,
    RetrievedItem,
    _EvaluationModel,
)
from assistant.evaluation.retrieval_adapter import to_evaluation_retrieved_items
from assistant.evaluation.retrieval_evaluator import (
    evaluate_retrieval,
    summarise_retrieval_results,
)
from assistant.schemas import ChatResponse

NO_EVALUABLE_EXPECTATIONS = "no_evaluable_expectations"


class EvaluationRunOptions(_EvaluationModel):
    """Safe, serializable controls for one evaluation run."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, frozen=True)

    retrieval_k: PositiveInt | None = None
    continue_on_error: StrictBool = True
    include_retrieved_content: StrictBool = False
    require_all_expected_sources: StrictBool = True
    answer_options: AnswerEvaluationOptions = Field(default_factory=AnswerEvaluationOptions)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class EvaluationRetrievalService(Protocol):
    """The existing production retrieval operation consumed by evaluation."""

    def retrieve(self, query: str) -> Sequence[KnowledgeChunk]: ...


class EvaluationAnswerService(Protocol):
    """Production answer generation from caller-supplied retrieved context."""

    def generate(
        self, *, question: str, retrieved_context: list[KnowledgeChunk]
    ) -> ChatResponse: ...


class Clock(Protocol):
    def now(self) -> datetime: ...


class _UtcClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class EvaluationRunner:
    """Execute validated evaluation cases sequentially without persistence."""

    def __init__(
        self,
        *,
        retrieval_service: EvaluationRetrievalService,
        answer_service: EvaluationAnswerService,
        clock: Clock | None = None,
        id_generator: Callable[[], str] | None = None,
    ) -> None:
        self._retrieval_service = retrieval_service
        self._answer_service = answer_service
        self._clock = clock or _UtcClock()
        self._id_generator = id_generator or (lambda: str(uuid4()))

    def run_case(
        self,
        case: EvaluationCase,
        *,
        options: EvaluationRunOptions | None = None,
    ) -> EvaluationCaseResult:
        """Run retrieval, generation, and deterministic checks for one case."""

        configured = options or EvaluationRunOptions()
        started_at = self._now()
        retrieval_result: RetrievalEvaluationResult | None = None
        try:
            production_items = list(self._retrieval_service.retrieve(case.question))
            adapted_items = to_evaluation_retrieved_items(production_items)
            stored_items = _stored_items(
                adapted_items,
                include_content=configured.include_retrieved_content,
            )
            retrieval_result = evaluate_retrieval(
                case=case,
                retrieved_items=stored_items,
                k=configured.retrieval_k,
            )
            response = self._answer_service.generate(
                question=case.question,
                retrieved_context=production_items,
            )
            answer_result = evaluate_chat_response(
                case=case,
                response=response,
                retrieved_items=retrieval_result.retrieved_items,
                options=configured.answer_options,
            )
            status = _case_status(
                retrieval_result,
                answer_result,
                require_all_expected_sources=configured.require_all_expected_sources,
            )
            completed_at = self._now()
            metadata: dict[str, JsonValue] = {}
            if status is EvaluationCaseStatus.SKIPPED:
                metadata["diagnostic_reasons"] = [NO_EVALUABLE_EXPECTATIONS]
            return EvaluationCaseResult(
                case_id=case.id,
                question=case.question,
                retrieval=retrieval_result,
                answer=answer_result,
                status=status,
                started_at=started_at,
                completed_at=completed_at,
                duration_ms=_duration_ms(started_at, completed_at),
                metadata=metadata,
            )
        except Exception as exc:
            completed_at = self._now()
            return EvaluationCaseResult(
                case_id=case.id,
                question=case.question,
                retrieval=retrieval_result,
                status=EvaluationCaseStatus.ERROR,
                started_at=started_at,
                completed_at=completed_at,
                duration_ms=_duration_ms(started_at, completed_at),
                error=f"evaluation case failed ({type(exc).__name__})",
            )

    def run_dataset(
        self,
        dataset: EvaluationDataset,
        *,
        options: EvaluationRunOptions | None = None,
    ) -> EvaluationRun:
        """Execute dataset cases in input order and return a complete in-memory run."""

        configured = options or EvaluationRunOptions()
        run_id = self._id_generator()
        started_at = self._now()
        results: list[EvaluationCaseResult] = []
        status = EvaluationRunStatus.COMPLETED

        for case in dataset.cases:
            result = self.run_case(case, options=configured)
            results.append(result)
            if result.status is EvaluationCaseStatus.ERROR and not configured.continue_on_error:
                status = EvaluationRunStatus.FAILED
                break

        completed_at = self._now()
        return EvaluationRun(
            id=run_id,
            dataset_name=dataset.name,
            dataset_version=dataset.version,
            status=status,
            results=results,
            schema_version=dataset.schema_version,
            started_at=started_at,
            completed_at=completed_at,
            summary=_summarise(dataset, results),
            configuration=_configuration_snapshot(configured),
            metadata=deepcopy(configured.metadata),
        )

    def _now(self) -> datetime:
        value = self._clock.now()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Evaluation clock must return a timezone-aware datetime")
        return value.astimezone(timezone.utc)


def _stored_items(items: Sequence[RetrievedItem], *, include_content: bool) -> list[RetrievedItem]:
    return [
        item.model_copy(deep=True, update={} if include_content else {"content": None})
        for item in items
    ]


def _case_status(
    retrieval: RetrievalEvaluationResult,
    answer: AnswerEvaluationResult,
    *,
    require_all_expected_sources: bool,
) -> EvaluationCaseStatus:
    retrieval_passed: bool | None
    if retrieval.hit is None:
        retrieval_passed = None
    elif not retrieval.hit:
        retrieval_passed = False
    elif require_all_expected_sources:
        retrieval_passed = retrieval.recall_at_k == 1.0
    else:
        retrieval_passed = True

    applicable = [value for value in (retrieval_passed, answer.passed) if value is not None]
    if not applicable:
        return EvaluationCaseStatus.SKIPPED
    if all(applicable):
        return EvaluationCaseStatus.PASSED
    return EvaluationCaseStatus.FAILED


def _summarise(
    dataset: EvaluationDataset,
    results: Sequence[EvaluationCaseResult],
) -> EvaluationSummary:
    retrieval_summary = summarise_retrieval_results(
        [result.retrieval for result in results if result.retrieval is not None]
    )
    answer_summary = summarise_answer_results(
        [result.answer for result in results if result.answer is not None]
    )
    durations = [result.duration_ms for result in results if result.duration_ms is not None]
    return EvaluationSummary(
        total_cases=len(dataset.cases),
        passed_cases=sum(result.status is EvaluationCaseStatus.PASSED for result in results),
        failed_cases=sum(result.status is EvaluationCaseStatus.FAILED for result in results),
        error_cases=sum(result.status is EvaluationCaseStatus.ERROR for result in results),
        skipped_cases=sum(result.status is EvaluationCaseStatus.SKIPPED for result in results),
        retrieval_precision_at_k=retrieval_summary.precision_at_k,
        retrieval_recall_at_k=retrieval_summary.recall_at_k,
        retrieval_hit_rate=retrieval_summary.hit_rate,
        mean_reciprocal_rank=retrieval_summary.mean_reciprocal_rank,
        answer_pass_rate=answer_summary.pass_rate,
        average_duration_ms=sum(durations) / len(durations) if durations else None,
    )


def _configuration_snapshot(options: EvaluationRunOptions) -> dict[str, JsonValue]:
    return {
        "retrieval_k": options.retrieval_k,
        "continue_on_error": options.continue_on_error,
        "include_retrieved_content": options.include_retrieved_content,
        "require_all_expected_sources": options.require_all_expected_sources,
        "answer_evaluation": options.answer_options.model_dump(mode="json"),
    }


def _duration_ms(started_at: datetime, completed_at: datetime) -> float:
    return (completed_at - started_at).total_seconds() * 1000
