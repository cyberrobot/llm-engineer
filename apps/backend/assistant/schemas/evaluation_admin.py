"""Explicit safe HTTP contracts for evaluation administration."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, StrictBool

from assistant.application.evaluation_admin import EvaluationDatasetResource
from assistant.evaluation import (
    AnswerEvaluationOptions,
    CaseComparisonResult,
    EvaluationComparisonResult,
    EvaluationRegressionPolicy,
    EvaluationReportMetadata,
    EvaluationRun,
    EvaluationRunOptions,
    MetricComparisonResult,
    MetricRegressionThreshold,
)


class _ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvaluationAdminErrorDetail(_ApiModel):
    code: str
    message: str


class EvaluationAdminErrorResponse(_ApiModel):
    detail: EvaluationAdminErrorDetail


class EvaluationDatasetSummaryResponse(_ApiModel):
    id: str
    name: str
    version: str
    schema_version: str
    case_count: int

    @classmethod
    def from_resource(cls, resource: EvaluationDatasetResource):
        return cls(
            id=resource.identifier,
            name=resource.dataset.name,
            version=resource.dataset.version,
            schema_version=resource.dataset.schema_version,
            case_count=len(resource.dataset.cases),
        )


class EvaluationDatasetListResponse(_ApiModel):
    items: list[EvaluationDatasetSummaryResponse]
    total: int


class EvaluationCaseDefinitionResponse(_ApiModel):
    id: str
    question: str
    expected_source_ids: list[str]
    expected_answer_contains: list[str]
    expected_answer_excludes: list[str]


class EvaluationDatasetDetailResponse(EvaluationDatasetSummaryResponse):
    description: str | None
    cases: list[EvaluationCaseDefinitionResponse]

    @classmethod
    def from_resource(cls, resource: EvaluationDatasetResource):
        dataset = resource.dataset
        return cls(
            **EvaluationDatasetSummaryResponse.from_resource(resource).model_dump(),
            description=dataset.description,
            cases=[
                EvaluationCaseDefinitionResponse(
                    id=case.id,
                    question=case.question,
                    expected_source_ids=list(case.expected_source_ids),
                    expected_answer_contains=list(case.expected_answer_contains),
                    expected_answer_excludes=list(case.expected_answer_excludes),
                )
                for case in dataset.cases
            ],
        )


class AnswerEvaluationOptionsRequest(_ApiModel):
    case_sensitive: StrictBool | None = None
    normalise_whitespace: StrictBool | None = None
    require_all_expected_fragments: StrictBool | None = None
    require_citations_when_sources_expected: StrictBool | None = None
    validate_citations_against_retrieval: StrictBool | None = None

    def to_domain(self) -> AnswerEvaluationOptions:
        return AnswerEvaluationOptions(**self.model_dump(exclude_none=True))


class EvaluationRunOptionsRequest(_ApiModel):
    retrieval_k: int | None = Field(default=None, strict=True, ge=1)
    continue_on_error: StrictBool | None = None
    require_all_expected_sources: StrictBool | None = None
    answer_options: AnswerEvaluationOptionsRequest | None = None

    def to_domain(self) -> EvaluationRunOptions:
        values = self.model_dump(exclude_none=True, exclude={"answer_options"})
        if self.answer_options is not None:
            values["answer_options"] = self.answer_options.to_domain()
        return EvaluationRunOptions(**values)


class ExecuteEvaluationRequest(_ApiModel):
    dataset_id: str = Field(min_length=1, max_length=128)
    persist_report: StrictBool = False
    options: EvaluationRunOptionsRequest | None = None

    def run_options(self) -> EvaluationRunOptions:
        return self.options.to_domain() if self.options is not None else EvaluationRunOptions()


class EvaluationRunConfigurationResponse(_ApiModel):
    retrieval_k: int | None = None
    continue_on_error: bool | None = None
    include_retrieved_content: bool | None = None
    require_all_expected_sources: bool | None = None
    answer_evaluation: dict[str, bool] | None = None


class EvaluationSummaryResponse(_ApiModel):
    total_cases: int
    passed_cases: int
    failed_cases: int
    error_cases: int
    skipped_cases: int
    retrieval_precision_at_k: float | None
    retrieval_recall_at_k: float | None
    retrieval_hit_rate: float | None
    mean_reciprocal_rank: float | None
    answer_pass_rate: float | None
    average_duration_ms: float | None


class RetrievedItemResponse(_ApiModel):
    id: str
    rank: int
    document_id: str | None
    chunk_id: str | None
    score: float | None
    distance: float | None


class RetrievalEvaluationResponse(_ApiModel):
    retrieved_items: list[RetrievedItemResponse]
    precision_at_k: float | None
    recall_at_k: float | None
    reciprocal_rank: float | None
    hit: bool | None
    expected_source_ids: list[str]
    matched_source_ids: list[str]
    unmatched_expected_source_ids: list[str]
    unexpected_retrieved_source_ids: list[str]
    duplicate_retrieved_source_ids: list[str]
    evaluated_at_k: int | None
    failure_reasons: list[str]


class AnswerEvaluationResponse(_ApiModel):
    passed: bool | None
    matched_expected_fragments: list[str]
    missing_expected_fragments: list[str]
    matched_excluded_fragments: list[str]
    citation_count: int | None
    citations_valid: bool | None
    hallucination_detected: bool | None
    cited_source_ids: list[str]
    valid_citation_source_ids: list[str]
    invalid_citation_source_ids: list[str]
    duplicate_citation_source_ids: list[str]
    cited_expected_source_ids: list[str]
    cited_unexpected_source_ids: list[str]
    uncited_expected_source_ids: list[str]
    failure_reasons: list[str]


class EvaluationCaseResultResponse(_ApiModel):
    case_id: str
    question: str
    retrieval: RetrievalEvaluationResponse | None
    answer: AnswerEvaluationResponse | None
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    duration_ms: float | None
    error: str | None
    diagnostics: list[str]


class EvaluationRunResponse(_ApiModel):
    id: str
    dataset_name: str
    dataset_version: str
    report_schema_version: str
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    configuration: EvaluationRunConfigurationResponse
    summary: EvaluationSummaryResponse | None
    results: list[EvaluationCaseResultResponse]

    @classmethod
    def from_domain(cls, run: EvaluationRun):
        return cls(
            id=run.id,
            dataset_name=run.dataset_name,
            dataset_version=run.dataset_version,
            report_schema_version=run.schema_version,
            status=run.status.value,
            started_at=run.started_at,
            completed_at=run.completed_at,
            configuration=_safe_configuration(run.configuration),
            summary=(
                EvaluationSummaryResponse(**run.summary.model_dump())
                if run.summary is not None
                else None
            ),
            results=[_case_response(result) for result in run.results],
        )


class EvaluationExecutionResponse(_ApiModel):
    run: EvaluationRunResponse
    report_persisted: bool


class EvaluationRunListItemResponse(_ApiModel):
    id: str
    dataset_name: str
    dataset_version: str
    report_schema_version: str
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    summary: EvaluationSummaryResponse | None

    @classmethod
    def from_domain(cls, run: EvaluationReportMetadata):
        return cls(
            id=run.id,
            dataset_name=run.dataset_name,
            dataset_version=run.dataset_version,
            report_schema_version=run.schema_version,
            status=run.status.value,
            started_at=run.started_at,
            completed_at=run.completed_at,
            summary=(
                EvaluationSummaryResponse(**run.summary.model_dump())
                if run.summary is not None
                else None
            ),
        )


class EvaluationRunListResponse(_ApiModel):
    items: list[EvaluationRunListItemResponse]
    total: int
    limit: int
    offset: int


class MetricRegressionThresholdRequest(_ApiModel):
    maximum_absolute_drop: float | None = Field(default=None, ge=0)
    maximum_relative_drop: float | None = Field(default=None, ge=0)

    def to_domain(self) -> MetricRegressionThreshold:
        return MetricRegressionThreshold(**self.model_dump(exclude_none=True))


class EvaluationComparisonOptionsRequest(_ApiModel):
    metric_thresholds: dict[str, MetricRegressionThresholdRequest] | None = None
    fail_on_new_failed_cases: StrictBool | None = None
    fail_on_new_error_cases: StrictBool | None = None
    fail_on_removed_cases: StrictBool | None = None
    fail_on_added_cases: StrictBool | None = None
    require_same_dataset_name: StrictBool | None = None
    require_same_dataset_version: StrictBool | None = None
    require_same_retrieval_k: StrictBool | None = None

    def to_domain(self) -> EvaluationRegressionPolicy:
        values = self.model_dump(exclude_none=True, exclude={"metric_thresholds"})
        if self.metric_thresholds is not None:
            values["metric_thresholds"] = {
                name: threshold.to_domain() for name, threshold in self.metric_thresholds.items()
            }
        return EvaluationRegressionPolicy(**values)


class CompareEvaluationRunsRequest(_ApiModel):
    candidate_run_id: str = Field(min_length=1, max_length=128)
    baseline_run_id: str = Field(min_length=1, max_length=128)
    options: EvaluationComparisonOptionsRequest | None = None

    def policy(self) -> EvaluationRegressionPolicy:
        return (
            self.options.to_domain() if self.options is not None else EvaluationRegressionPolicy()
        )


class EvaluationComparisonResponse(_ApiModel):
    baseline_run_id: str
    current_run_id: str
    baseline_dataset_name: str
    current_dataset_name: str
    baseline_dataset_version: str | None
    current_dataset_version: str | None
    compatible: bool
    compatibility_errors: list[str]
    compatibility_warnings: list[str]
    metric_results: list[MetricComparisonResult]
    case_results: list[CaseComparisonResult]
    added_case_ids: list[str]
    removed_case_ids: list[str]
    newly_failed_case_ids: list[str]
    newly_errored_case_ids: list[str]
    recovered_case_ids: list[str]
    compared_case_count: int
    added_case_count: int
    removed_case_count: int
    newly_failed_case_count: int
    newly_errored_case_count: int
    recovered_case_count: int
    metric_regression_count: int
    regressed: bool
    regression_reasons: list[str]

    @classmethod
    def from_domain(cls, result: EvaluationComparisonResult):
        return cls.model_validate(result.model_dump())


def _safe_configuration(configuration: dict[str, Any]) -> EvaluationRunConfigurationResponse:
    answer = configuration.get("answer_evaluation")
    safe_answer = None
    if isinstance(answer, dict):
        allowed = {
            key: value
            for key, value in answer.items()
            if key
            in {
                "case_sensitive",
                "normalise_whitespace",
                "require_all_expected_fragments",
                "require_citations_when_sources_expected",
                "validate_citations_against_retrieval",
            }
            and isinstance(value, bool)
        }
        safe_answer = allowed or None
    retrieval_k = configuration.get("retrieval_k")
    return EvaluationRunConfigurationResponse(
        retrieval_k=retrieval_k if isinstance(retrieval_k, int) and retrieval_k > 0 else None,
        continue_on_error=_safe_bool(configuration.get("continue_on_error")),
        include_retrieved_content=_safe_bool(configuration.get("include_retrieved_content")),
        require_all_expected_sources=_safe_bool(configuration.get("require_all_expected_sources")),
        answer_evaluation=safe_answer,
    )


def _safe_bool(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def _case_response(result) -> EvaluationCaseResultResponse:
    retrieval = None
    if result.retrieval is not None:
        values = result.retrieval.model_dump(exclude={"retrieved_items", "metadata"})
        values["retrieved_items"] = [
            RetrievedItemResponse(
                id=item.id,
                rank=item.rank,
                document_id=item.document_id,
                chunk_id=item.chunk_id,
                score=item.score,
                distance=item.distance,
            )
            for item in result.retrieval.retrieved_items
        ]
        retrieval = RetrievalEvaluationResponse(**values)
    answer = None
    if result.answer is not None:
        answer = AnswerEvaluationResponse(
            **result.answer.model_dump(exclude={"answer", "metadata"})
        )
    diagnostic_values = result.metadata.get("diagnostic_reasons")
    diagnostics = (
        [value for value in diagnostic_values if isinstance(value, str)]
        if isinstance(diagnostic_values, list)
        else []
    )
    return EvaluationCaseResultResponse(
        case_id=result.case_id,
        question=result.question,
        retrieval=retrieval,
        answer=answer,
        status=result.status.value,
        started_at=result.started_at,
        completed_at=result.completed_at,
        duration_ms=result.duration_ms,
        error=result.error,
        diagnostics=diagnostics,
    )
