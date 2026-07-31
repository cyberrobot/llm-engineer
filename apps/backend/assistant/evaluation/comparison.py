"""Pure, deterministic comparison of persisted evaluation run contracts."""

from enum import Enum
from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from assistant.evaluation.models import (
    EvaluationCaseResult,
    EvaluationCaseStatus,
    EvaluationRun,
    EvaluationRunStatus,
)
from assistant.evaluation.reporting import load_evaluation_report


class _ComparisonModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class MetricDirection(str, Enum):
    HIGHER_IS_BETTER = "higher_is_better"


class MetricComparisonStatus(str, Enum):
    IMPROVED = "improved"
    UNCHANGED = "unchanged"
    REGRESSED = "regressed"
    WITHIN_TOLERANCE = "within_tolerance"
    NEW = "new"
    BECAME_UNEVALUABLE = "became_unevaluable"
    NOT_COMPARABLE = "not_comparable"


class CaseStatusTransition(str, Enum):
    UNCHANGED_PASS = "unchanged_pass"
    UNCHANGED_FAIL = "unchanged_fail"
    UNCHANGED_ERROR = "unchanged_error"
    UNCHANGED_SKIP = "unchanged_skip"
    PASS_TO_FAIL = "pass_to_fail"
    PASS_TO_ERROR = "pass_to_error"
    PASS_TO_SKIP = "pass_to_skip"
    FAIL_TO_PASS = "fail_to_pass"
    FAIL_TO_ERROR = "fail_to_error"
    FAIL_TO_SKIP = "fail_to_skip"
    ERROR_TO_PASS = "error_to_pass"
    ERROR_TO_FAIL = "error_to_fail"
    ERROR_TO_SKIP = "error_to_skip"
    SKIP_TO_PASS = "skip_to_pass"
    SKIP_TO_FAIL = "skip_to_fail"
    SKIP_TO_ERROR = "skip_to_error"
    ADDED = "added"
    REMOVED = "removed"


_SUPPORTED_REGRESSION_METRICS: dict[str, MetricDirection] = {
    "retrieval_precision_at_k": MetricDirection.HIGHER_IS_BETTER,
    "retrieval_recall_at_k": MetricDirection.HIGHER_IS_BETTER,
    "retrieval_hit_rate": MetricDirection.HIGHER_IS_BETTER,
    "mean_reciprocal_rank": MetricDirection.HIGHER_IS_BETTER,
    "answer_pass_rate": MetricDirection.HIGHER_IS_BETTER,
}

_TERMINAL_RUN_STATUSES = frozenset({EvaluationRunStatus.COMPLETED, EvaluationRunStatus.FAILED})
_THRESHOLD_EPSILON = 1e-12
_SEMANTIC_CONFIGURATION_FIELDS = (
    "require_all_expected_sources",
    "answer_evaluation",
)


class MetricRegressionThreshold(_ComparisonModel):
    """Allowed quality-metric decreases, expressed as decimal values."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, frozen=True)

    maximum_absolute_drop: float | None = Field(default=None, ge=0)
    maximum_relative_drop: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def require_one_threshold(self) -> Self:
        if self.maximum_absolute_drop is None and self.maximum_relative_drop is None:
            raise ValueError("At least one regression threshold must be supplied")
        return self


class EvaluationRegressionPolicy(_ComparisonModel):
    """Validation-backed controls for deterministic regression decisions."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, frozen=True)

    metric_thresholds: dict[str, MetricRegressionThreshold] = Field(default_factory=dict)
    fail_on_new_failed_cases: bool = True
    fail_on_new_error_cases: bool = True
    fail_on_removed_cases: bool = False
    fail_on_added_cases: bool = False
    require_same_dataset_name: bool = True
    require_same_dataset_version: bool = False
    require_same_retrieval_k: bool = True

    @model_validator(mode="after")
    def reject_unsupported_metrics(self) -> Self:
        unsupported = [
            metric
            for metric in self.metric_thresholds
            if metric not in _SUPPORTED_REGRESSION_METRICS
        ]
        if unsupported:
            names = ", ".join(unsupported)
            raise ValueError(f"Unsupported regression metric: {names}")
        return self


class RunCompatibilityResult(_ComparisonModel):
    compatible: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class MetricComparisonResult(_ComparisonModel):
    metric: str
    baseline_value: float | None
    current_value: float | None
    delta: float | None
    absolute_drop: float | None
    relative_drop: float | None
    threshold: MetricRegressionThreshold | None
    status: MetricComparisonStatus
    regressed: bool
    reasons: list[str] = Field(default_factory=list)


class CaseComparisonResult(_ComparisonModel):
    case_id: str
    baseline_status: EvaluationCaseStatus | None
    current_status: EvaluationCaseStatus | None
    transition: CaseStatusTransition
    regressed: bool
    improved: bool
    baseline_failure_reasons: list[str] = Field(default_factory=list)
    current_failure_reasons: list[str] = Field(default_factory=list)


class EvaluationComparisonResult(_ComparisonModel):
    baseline_run_id: str
    current_run_id: str
    baseline_dataset_name: str
    current_dataset_name: str
    baseline_dataset_version: str | None
    current_dataset_version: str | None
    compatible: bool
    compatibility_errors: list[str] = Field(default_factory=list)
    compatibility_warnings: list[str] = Field(default_factory=list)
    metric_results: list[MetricComparisonResult] = Field(default_factory=list)
    case_results: list[CaseComparisonResult] = Field(default_factory=list)
    added_case_ids: list[str] = Field(default_factory=list)
    removed_case_ids: list[str] = Field(default_factory=list)
    newly_failed_case_ids: list[str] = Field(default_factory=list)
    newly_errored_case_ids: list[str] = Field(default_factory=list)
    recovered_case_ids: list[str] = Field(default_factory=list)
    compared_case_count: int = Field(ge=0)
    added_case_count: int = Field(ge=0)
    removed_case_count: int = Field(ge=0)
    newly_failed_case_count: int = Field(ge=0)
    newly_errored_case_count: int = Field(ge=0)
    recovered_case_count: int = Field(ge=0)
    metric_regression_count: int = Field(ge=0)
    regressed: bool
    regression_reasons: list[str] = Field(default_factory=list)


_TRANSITIONS: dict[tuple[EvaluationCaseStatus, EvaluationCaseStatus], CaseStatusTransition] = {
    (EvaluationCaseStatus.PASSED, EvaluationCaseStatus.PASSED): (
        CaseStatusTransition.UNCHANGED_PASS
    ),
    (EvaluationCaseStatus.PASSED, EvaluationCaseStatus.FAILED): (CaseStatusTransition.PASS_TO_FAIL),
    (EvaluationCaseStatus.PASSED, EvaluationCaseStatus.ERROR): (CaseStatusTransition.PASS_TO_ERROR),
    (EvaluationCaseStatus.PASSED, EvaluationCaseStatus.SKIPPED): (
        CaseStatusTransition.PASS_TO_SKIP
    ),
    (EvaluationCaseStatus.FAILED, EvaluationCaseStatus.PASSED): (CaseStatusTransition.FAIL_TO_PASS),
    (EvaluationCaseStatus.FAILED, EvaluationCaseStatus.FAILED): (
        CaseStatusTransition.UNCHANGED_FAIL
    ),
    (EvaluationCaseStatus.FAILED, EvaluationCaseStatus.ERROR): (CaseStatusTransition.FAIL_TO_ERROR),
    (EvaluationCaseStatus.FAILED, EvaluationCaseStatus.SKIPPED): (
        CaseStatusTransition.FAIL_TO_SKIP
    ),
    (EvaluationCaseStatus.ERROR, EvaluationCaseStatus.PASSED): (CaseStatusTransition.ERROR_TO_PASS),
    (EvaluationCaseStatus.ERROR, EvaluationCaseStatus.FAILED): (CaseStatusTransition.ERROR_TO_FAIL),
    (EvaluationCaseStatus.ERROR, EvaluationCaseStatus.ERROR): (
        CaseStatusTransition.UNCHANGED_ERROR
    ),
    (EvaluationCaseStatus.ERROR, EvaluationCaseStatus.SKIPPED): (
        CaseStatusTransition.ERROR_TO_SKIP
    ),
    (EvaluationCaseStatus.SKIPPED, EvaluationCaseStatus.PASSED): (
        CaseStatusTransition.SKIP_TO_PASS
    ),
    (EvaluationCaseStatus.SKIPPED, EvaluationCaseStatus.FAILED): (
        CaseStatusTransition.SKIP_TO_FAIL
    ),
    (EvaluationCaseStatus.SKIPPED, EvaluationCaseStatus.ERROR): (
        CaseStatusTransition.SKIP_TO_ERROR
    ),
    (EvaluationCaseStatus.SKIPPED, EvaluationCaseStatus.SKIPPED): (
        CaseStatusTransition.UNCHANGED_SKIP
    ),
}

_REGRESSED_TRANSITIONS = frozenset(
    {
        CaseStatusTransition.PASS_TO_FAIL,
        CaseStatusTransition.PASS_TO_ERROR,
        CaseStatusTransition.PASS_TO_SKIP,
        CaseStatusTransition.FAIL_TO_ERROR,
        CaseStatusTransition.SKIP_TO_FAIL,
        CaseStatusTransition.SKIP_TO_ERROR,
    }
)
_IMPROVED_TRANSITIONS = frozenset(
    {
        CaseStatusTransition.FAIL_TO_PASS,
        CaseStatusTransition.ERROR_TO_PASS,
        CaseStatusTransition.SKIP_TO_PASS,
        CaseStatusTransition.ERROR_TO_FAIL,
    }
)
_RECOVERED_TRANSITIONS = frozenset(
    {
        CaseStatusTransition.FAIL_TO_PASS,
        CaseStatusTransition.ERROR_TO_PASS,
        CaseStatusTransition.SKIP_TO_PASS,
    }
)


def validate_run_compatibility(
    *,
    baseline: EvaluationRun,
    current: EvaluationRun,
    policy: EvaluationRegressionPolicy | None = None,
) -> RunCompatibilityResult:
    """Validate whether two runs have meaningfully comparable result contracts."""

    configured = policy or EvaluationRegressionPolicy()
    errors: list[str] = []
    warnings: list[str] = []

    if baseline.schema_version != current.schema_version:
        errors.append("report_schema_version_differs")
    if baseline.dataset_name != current.dataset_name:
        target = errors if configured.require_same_dataset_name else warnings
        target.append("dataset_name_differs")
    if baseline.dataset_version != current.dataset_version:
        target = errors if configured.require_same_dataset_version else warnings
        target.append("dataset_version_differs")

    baseline_k = baseline.configuration.get("retrieval_k")
    current_k = current.configuration.get("retrieval_k")
    if baseline_k != current_k:
        target = errors if configured.require_same_retrieval_k else warnings
        target.append("retrieval_k_differs")

    if baseline.status not in _TERMINAL_RUN_STATUSES:
        errors.append("baseline_run_not_terminal")
    elif baseline.status is EvaluationRunStatus.FAILED:
        warnings.append("baseline_run_failed")
    if current.status not in _TERMINAL_RUN_STATUSES:
        errors.append("current_run_not_terminal")
    elif current.status is EvaluationRunStatus.FAILED:
        warnings.append("current_run_failed")

    if baseline.summary is None:
        errors.append("baseline_summary_missing")
    if current.summary is None:
        errors.append("current_summary_missing")

    if any(result.status is EvaluationCaseStatus.PENDING for result in baseline.results):
        errors.append("baseline_case_status_not_terminal")
    if any(result.status is EvaluationCaseStatus.PENDING for result in current.results):
        errors.append("current_case_status_not_terminal")

    if _duplicate_case_ids(baseline.results):
        errors.append("duplicate_baseline_case_id")
    if _duplicate_case_ids(current.results):
        errors.append("duplicate_current_case_id")

    if _semantic_configuration(baseline) != _semantic_configuration(current):
        warnings.append("evaluation_configuration_differs")

    return RunCompatibilityResult(
        compatible=not errors,
        errors=errors,
        warnings=warnings,
    )


def compare_evaluation_runs(
    *,
    baseline: EvaluationRun,
    current: EvaluationRun,
    policy: EvaluationRegressionPolicy | None = None,
) -> EvaluationComparisonResult:
    """Compare two runs without recalculation, mutation, I/O, or generated state."""

    configured = policy or EvaluationRegressionPolicy()
    compatibility = validate_run_compatibility(
        baseline=baseline,
        current=current,
        policy=configured,
    )
    if not compatibility.compatible:
        return _result(
            baseline=baseline,
            current=current,
            compatibility=compatibility,
        )

    metric_results = _compare_metrics(baseline, current, configured)
    case_results = _compare_cases(baseline.results, current.results)

    added_case_ids = [
        result.case_id for result in case_results if result.transition is CaseStatusTransition.ADDED
    ]
    removed_case_ids = [
        result.case_id
        for result in case_results
        if result.transition is CaseStatusTransition.REMOVED
    ]
    newly_failed_case_ids = [
        result.case_id
        for result in case_results
        if result.transition
        in {CaseStatusTransition.PASS_TO_FAIL, CaseStatusTransition.SKIP_TO_FAIL}
    ]
    newly_errored_case_ids = [
        result.case_id
        for result in case_results
        if result.current_status is EvaluationCaseStatus.ERROR
        and result.baseline_status is not None
        and result.baseline_status is not EvaluationCaseStatus.ERROR
    ]
    recovered_case_ids = [
        result.case_id for result in case_results if result.transition in _RECOVERED_TRANSITIONS
    ]

    regression_reasons: list[str] = []
    if any(
        result.regressed
        and result.threshold is not None
        and result.status is MetricComparisonStatus.REGRESSED
        for result in metric_results
    ):
        regression_reasons.append("metric_threshold_breached")
    if any(
        result.regressed and result.status is MetricComparisonStatus.BECAME_UNEVALUABLE
        for result in metric_results
    ):
        regression_reasons.append("metric_became_unevaluable")
    if newly_failed_case_ids and configured.fail_on_new_failed_cases:
        regression_reasons.append("new_failed_case")
    if newly_errored_case_ids and configured.fail_on_new_error_cases:
        regression_reasons.append("new_error_case")

    added_results = [
        result for result in case_results if result.transition is CaseStatusTransition.ADDED
    ]
    if any(result.current_status is EvaluationCaseStatus.FAILED for result in added_results):
        regression_reasons.append("added_failing_case")
    if any(result.current_status is EvaluationCaseStatus.ERROR for result in added_results):
        regression_reasons.append("added_error_case")
    if added_case_ids and configured.fail_on_added_cases:
        regression_reasons.append("added_case")
    if removed_case_ids and configured.fail_on_removed_cases:
        regression_reasons.append("removed_case")

    return _result(
        baseline=baseline,
        current=current,
        compatibility=compatibility,
        metric_results=metric_results,
        case_results=case_results,
        added_case_ids=added_case_ids,
        removed_case_ids=removed_case_ids,
        newly_failed_case_ids=newly_failed_case_ids,
        newly_errored_case_ids=newly_errored_case_ids,
        recovered_case_ids=recovered_case_ids,
        regression_reasons=regression_reasons,
    )


def compare_evaluation_report_files(
    *,
    baseline_path: str | Path,
    current_path: str | Path,
    policy: EvaluationRegressionPolicy | None = None,
) -> EvaluationComparisonResult:
    """Load two persisted reports through the canonical loader and compare them."""

    baseline = load_evaluation_report(baseline_path)
    current = load_evaluation_report(current_path)
    return compare_evaluation_runs(baseline=baseline, current=current, policy=policy)


def _result(
    *,
    baseline: EvaluationRun,
    current: EvaluationRun,
    compatibility: RunCompatibilityResult,
    metric_results: list[MetricComparisonResult] | None = None,
    case_results: list[CaseComparisonResult] | None = None,
    added_case_ids: list[str] | None = None,
    removed_case_ids: list[str] | None = None,
    newly_failed_case_ids: list[str] | None = None,
    newly_errored_case_ids: list[str] | None = None,
    recovered_case_ids: list[str] | None = None,
    regression_reasons: list[str] | None = None,
) -> EvaluationComparisonResult:
    metrics = metric_results or []
    cases = case_results or []
    added = added_case_ids or []
    removed = removed_case_ids or []
    newly_failed = newly_failed_case_ids or []
    newly_errored = newly_errored_case_ids or []
    recovered = recovered_case_ids or []
    reasons = regression_reasons or []
    return EvaluationComparisonResult(
        baseline_run_id=baseline.id,
        current_run_id=current.id,
        baseline_dataset_name=baseline.dataset_name,
        current_dataset_name=current.dataset_name,
        baseline_dataset_version=baseline.dataset_version,
        current_dataset_version=current.dataset_version,
        compatible=compatibility.compatible,
        compatibility_errors=compatibility.errors,
        compatibility_warnings=compatibility.warnings,
        metric_results=metrics,
        case_results=cases,
        added_case_ids=added,
        removed_case_ids=removed,
        newly_failed_case_ids=newly_failed,
        newly_errored_case_ids=newly_errored,
        recovered_case_ids=recovered,
        compared_case_count=sum(
            case.transition not in {CaseStatusTransition.ADDED, CaseStatusTransition.REMOVED}
            for case in cases
        ),
        added_case_count=len(added),
        removed_case_count=len(removed),
        newly_failed_case_count=len(newly_failed),
        newly_errored_case_count=len(newly_errored),
        recovered_case_count=len(recovered),
        metric_regression_count=sum(metric.regressed for metric in metrics),
        regressed=bool(reasons) if compatibility.compatible else False,
        regression_reasons=reasons if compatibility.compatible else [],
    )


def _compare_metrics(
    baseline: EvaluationRun,
    current: EvaluationRun,
    policy: EvaluationRegressionPolicy,
) -> list[MetricComparisonResult]:
    assert baseline.summary is not None
    assert current.summary is not None
    return [
        _compare_metric(
            metric=metric,
            baseline_value=getattr(baseline.summary, metric),
            current_value=getattr(current.summary, metric),
            threshold=policy.metric_thresholds.get(metric),
        )
        for metric in _SUPPORTED_REGRESSION_METRICS
    ]


def _compare_metric(
    *,
    metric: str,
    baseline_value: float | None,
    current_value: float | None,
    threshold: MetricRegressionThreshold | None,
) -> MetricComparisonResult:
    if baseline_value is None and current_value is None:
        return MetricComparisonResult(
            metric=metric,
            baseline_value=None,
            current_value=None,
            delta=None,
            absolute_drop=None,
            relative_drop=None,
            threshold=threshold,
            status=MetricComparisonStatus.NOT_COMPARABLE,
            regressed=False,
        )
    if baseline_value is None:
        return MetricComparisonResult(
            metric=metric,
            baseline_value=None,
            current_value=current_value,
            delta=None,
            absolute_drop=None,
            relative_drop=None,
            threshold=threshold,
            status=MetricComparisonStatus.NEW,
            regressed=False,
        )
    if current_value is None:
        return MetricComparisonResult(
            metric=metric,
            baseline_value=baseline_value,
            current_value=None,
            delta=None,
            absolute_drop=None,
            relative_drop=None,
            threshold=threshold,
            status=MetricComparisonStatus.BECAME_UNEVALUABLE,
            regressed=threshold is not None,
            reasons=["metric_became_unevaluable"] if threshold is not None else [],
        )

    delta = current_value - baseline_value
    absolute_drop = max(baseline_value - current_value, 0.0)
    relative_drop = 0.0 if baseline_value == 0 else absolute_drop / abs(baseline_value)
    if delta > 0:
        status = MetricComparisonStatus.IMPROVED
        breached = False
        reasons: list[str] = []
    elif delta == 0:
        status = MetricComparisonStatus.UNCHANGED
        breached = False
        reasons = []
    elif threshold is None:
        status = MetricComparisonStatus.REGRESSED
        breached = True
        reasons = ["metric_decreased_without_threshold"]
    else:
        reasons = []
        if (
            threshold.maximum_absolute_drop is not None
            and absolute_drop - threshold.maximum_absolute_drop > _THRESHOLD_EPSILON
        ):
            reasons.append("absolute_drop_exceeded")
        if (
            threshold.maximum_relative_drop is not None
            and relative_drop - threshold.maximum_relative_drop > _THRESHOLD_EPSILON
        ):
            reasons.append("relative_drop_exceeded")
        breached = bool(reasons)
        status = (
            MetricComparisonStatus.REGRESSED
            if breached
            else MetricComparisonStatus.WITHIN_TOLERANCE
        )

    return MetricComparisonResult(
        metric=metric,
        baseline_value=baseline_value,
        current_value=current_value,
        delta=delta,
        absolute_drop=absolute_drop,
        relative_drop=relative_drop,
        threshold=threshold,
        status=status,
        regressed=breached,
        reasons=reasons,
    )


def _compare_cases(
    baseline_results: list[EvaluationCaseResult],
    current_results: list[EvaluationCaseResult],
) -> list[CaseComparisonResult]:
    baseline_by_id = {result.case_id: result for result in baseline_results}
    current_ids = {result.case_id for result in current_results}
    compared: list[CaseComparisonResult] = []

    for current in current_results:
        baseline = baseline_by_id.get(current.case_id)
        if baseline is None:
            compared.append(
                CaseComparisonResult(
                    case_id=current.case_id,
                    baseline_status=None,
                    current_status=current.status,
                    transition=CaseStatusTransition.ADDED,
                    regressed=current.status
                    in {EvaluationCaseStatus.FAILED, EvaluationCaseStatus.ERROR},
                    improved=False,
                    current_failure_reasons=_failure_reasons(current),
                )
            )
            continue
        transition = _TRANSITIONS[(baseline.status, current.status)]
        compared.append(
            CaseComparisonResult(
                case_id=current.case_id,
                baseline_status=baseline.status,
                current_status=current.status,
                transition=transition,
                regressed=transition in _REGRESSED_TRANSITIONS,
                improved=transition in _IMPROVED_TRANSITIONS,
                baseline_failure_reasons=_failure_reasons(baseline),
                current_failure_reasons=_failure_reasons(current),
            )
        )

    for baseline in baseline_results:
        if baseline.case_id not in current_ids:
            compared.append(
                CaseComparisonResult(
                    case_id=baseline.case_id,
                    baseline_status=baseline.status,
                    current_status=None,
                    transition=CaseStatusTransition.REMOVED,
                    regressed=False,
                    improved=False,
                    baseline_failure_reasons=_failure_reasons(baseline),
                )
            )
    return compared


def _failure_reasons(result: EvaluationCaseResult) -> list[str]:
    reasons: list[str] = []
    if result.retrieval is not None:
        reasons.extend(result.retrieval.failure_reasons)
    if result.answer is not None:
        reasons.extend(result.answer.failure_reasons)
    if result.error is not None:
        reasons.append(result.error)
    diagnostic_reasons = result.metadata.get("diagnostic_reasons")
    if isinstance(diagnostic_reasons, list):
        reasons.extend(reason for reason in diagnostic_reasons if isinstance(reason, str))
    return list(dict.fromkeys(reasons))


def _duplicate_case_ids(results: list[EvaluationCaseResult]) -> bool:
    ids = [result.case_id for result in results]
    return len(ids) != len(set(ids))


def _semantic_configuration(run: EvaluationRun) -> tuple[object, ...]:
    return tuple(run.configuration.get(field) for field in _SEMANTIC_CONFIGURATION_FIELDS)
