from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

import pytest
from pydantic import ValidationError

from assistant.evaluation import (
    AnswerEvaluationResult,
    CaseStatusTransition,
    EvaluationCaseResult,
    EvaluationCaseStatus,
    EvaluationRegressionPolicy,
    EvaluationRun,
    EvaluationRunStatus,
    EvaluationSummary,
    MetricComparisonStatus,
    MetricRegressionThreshold,
    RetrievalEvaluationResult,
    compare_evaluation_report_files,
    compare_evaluation_runs,
    save_evaluation_report,
    validate_run_compatibility,
)


def _summary(**overrides: object) -> EvaluationSummary:
    values: dict[str, Any] = {
        "total_cases": 4,
        "passed_cases": 2,
        "failed_cases": 1,
        "error_cases": 1,
        "skipped_cases": 0,
        "retrieval_precision_at_k": 0.8,
        "retrieval_recall_at_k": 0.9,
        "retrieval_hit_rate": 0.95,
        "mean_reciprocal_rank": 0.82,
        "answer_pass_rate": 0.85,
        "average_duration_ms": 10.0,
    }
    values.update(overrides)
    return EvaluationSummary(**values)


def _case(
    case_id: str,
    status: EvaluationCaseStatus,
    *,
    retrieval_reasons: list[str] | None = None,
    answer_reasons: list[str] | None = None,
    error: str | None = None,
) -> EvaluationCaseResult:
    return EvaluationCaseResult(
        case_id=case_id,
        question=f"Question for {case_id}?",
        status=status,
        retrieval=(
            RetrievalEvaluationResult(
                retrieved_items=[],
                failure_reasons=retrieval_reasons or [],
            )
            if retrieval_reasons is not None
            else None
        ),
        answer=(
            AnswerEvaluationResult(answer="not exposed", failure_reasons=answer_reasons or [])
            if answer_reasons is not None
            else None
        ),
        error=error,
    )


def _run(
    run_id: str,
    *,
    results: list[EvaluationCaseResult] | None = None,
    summary: EvaluationSummary | None = None,
    dataset_name: str = "support-knowledge-baseline",
    dataset_version: str = "2026.07",
    status: EvaluationRunStatus = EvaluationRunStatus.COMPLETED,
    schema_version: str = "1.0",
    retrieval_k: int | None = 5,
    configuration: dict[str, Any] | None = None,
) -> EvaluationRun:
    return EvaluationRun(
        id=run_id,
        dataset_name=dataset_name,
        dataset_version=dataset_version,
        schema_version=schema_version,
        status=status,
        results=results
        or [
            _case("case-a", EvaluationCaseStatus.PASSED),
            _case("case-b", EvaluationCaseStatus.PASSED),
            _case("case-c", EvaluationCaseStatus.FAILED),
            _case("case-d", EvaluationCaseStatus.ERROR, error="safe error"),
        ],
        summary=summary or _summary(),
        started_at=datetime(2026, 7, 30, 9, 0, tzinfo=timezone.utc),
        completed_at=datetime(2026, 7, 30, 9, 1, tzinfo=timezone.utc),
        configuration=configuration
        or {
            "retrieval_k": retrieval_k,
            "require_all_expected_sources": True,
            "answer_evaluation": {
                "case_sensitive": False,
                "normalise_whitespace": True,
                "require_all_expected_fragments": True,
                "require_citations_when_sources_expected": True,
                "validate_citations_against_retrieval": True,
            },
        },
    )


def _metric(result, metric: str):
    return next(item for item in result.metric_results if item.metric == metric)


def _case_result(result, case_id: str):
    return next(item for item in result.case_results if item.case_id == case_id)


def test_policy_validates_thresholds_supported_metrics_and_safe_defaults():
    with pytest.raises(ValidationError):
        MetricRegressionThreshold()
    with pytest.raises(ValidationError):
        MetricRegressionThreshold(maximum_absolute_drop=-0.01)
    with pytest.raises(ValidationError):
        MetricRegressionThreshold(maximum_relative_drop=-0.01)

    absolute = MetricRegressionThreshold(maximum_absolute_drop=0.02)
    relative = MetricRegressionThreshold(maximum_relative_drop=0.05)
    combined = MetricRegressionThreshold(
        maximum_absolute_drop=0.02,
        maximum_relative_drop=0.05,
    )
    assert absolute.maximum_relative_drop is None
    assert relative.maximum_absolute_drop is None
    assert combined.maximum_absolute_drop == 0.02

    first = EvaluationRegressionPolicy()
    second = EvaluationRegressionPolicy()
    first.metric_thresholds["retrieval_recall_at_k"] = absolute
    assert second.metric_thresholds == {}

    with pytest.raises(ValidationError, match="Unsupported regression metric"):
        EvaluationRegressionPolicy(metric_thresholds={"total_cases": absolute})


@pytest.mark.parametrize(
    ("baseline", "current", "threshold", "status", "regressed"),
    [
        (0.8, 0.8, None, MetricComparisonStatus.UNCHANGED, False),
        (0.8, 0.9, None, MetricComparisonStatus.IMPROVED, False),
        (0.8, 0.7, None, MetricComparisonStatus.REGRESSED, True),
        (
            0.8,
            0.79,
            MetricRegressionThreshold(maximum_absolute_drop=0.02),
            MetricComparisonStatus.WITHIN_TOLERANCE,
            False,
        ),
        (
            0.8,
            0.77,
            MetricRegressionThreshold(maximum_absolute_drop=0.02),
            MetricComparisonStatus.REGRESSED,
            True,
        ),
        (
            0.8,
            0.78,
            MetricRegressionThreshold(maximum_absolute_drop=0.02),
            MetricComparisonStatus.WITHIN_TOLERANCE,
            False,
        ),
        (
            0.8,
            0.75,
            MetricRegressionThreshold(maximum_relative_drop=0.10),
            MetricComparisonStatus.WITHIN_TOLERANCE,
            False,
        ),
        (
            0.8,
            0.70,
            MetricRegressionThreshold(maximum_relative_drop=0.10),
            MetricComparisonStatus.REGRESSED,
            True,
        ),
        (
            0.8,
            0.75,
            MetricRegressionThreshold(
                maximum_absolute_drop=0.1,
                maximum_relative_drop=0.05,
            ),
            MetricComparisonStatus.REGRESSED,
            True,
        ),
    ],
)
def test_metric_threshold_semantics(baseline, current, threshold, status, regressed):
    policy = EvaluationRegressionPolicy(
        metric_thresholds={"retrieval_recall_at_k": threshold} if threshold else {}
    )
    result = compare_evaluation_runs(
        baseline=_run("baseline", summary=_summary(retrieval_recall_at_k=baseline)),
        current=_run("current", summary=_summary(retrieval_recall_at_k=current)),
        policy=policy,
    )

    metric = _metric(result, "retrieval_recall_at_k")
    assert metric.status is status
    assert metric.regressed is regressed
    assert metric.delta == pytest.approx(current - baseline)
    assert metric.absolute_drop == pytest.approx(max(baseline - current, 0.0))
    assert result.regressed is (regressed and threshold is not None)


@pytest.mark.parametrize(
    ("baseline", "current", "expected_status", "expected_relative", "regressed"),
    [
        (0.0, 0.0, MetricComparisonStatus.UNCHANGED, 0.0, False),
        (0.0, 0.1, MetricComparisonStatus.IMPROVED, 0.0, False),
        (None, 0.5, MetricComparisonStatus.NEW, None, False),
        (0.5, None, MetricComparisonStatus.BECAME_UNEVALUABLE, None, True),
        (None, None, MetricComparisonStatus.NOT_COMPARABLE, None, False),
    ],
)
def test_missing_and_zero_metric_values_are_explicit(
    baseline, current, expected_status, expected_relative, regressed
):
    threshold = MetricRegressionThreshold(maximum_relative_drop=0.1)
    result = compare_evaluation_runs(
        baseline=_run("baseline", summary=_summary(answer_pass_rate=baseline)),
        current=_run("current", summary=_summary(answer_pass_rate=current)),
        policy=EvaluationRegressionPolicy(metric_thresholds={"answer_pass_rate": threshold}),
    )

    metric = _metric(result, "answer_pass_rate")
    assert metric.status is expected_status
    assert metric.relative_drop == expected_relative
    assert metric.regressed is regressed


def test_all_supported_metrics_are_compared_in_stable_order_without_rounding():
    baseline = _run("baseline")
    current = _run(
        "current",
        summary=_summary(
            retrieval_precision_at_k=0.799999999,
            retrieval_recall_at_k=0.899999999,
            retrieval_hit_rate=0.949999999,
            mean_reciprocal_rank=0.819999999,
            answer_pass_rate=0.849999999,
        ),
    )
    result = compare_evaluation_runs(baseline=baseline, current=current)

    assert [item.metric for item in result.metric_results] == [
        "retrieval_precision_at_k",
        "retrieval_recall_at_k",
        "retrieval_hit_rate",
        "mean_reciprocal_rank",
        "answer_pass_rate",
    ]
    assert result.metric_results[0].delta == pytest.approx(-0.000000001)
    assert result.metric_results[0].delta != 0.0


@pytest.mark.parametrize(
    "metric",
    [
        "retrieval_precision_at_k",
        "retrieval_recall_at_k",
        "retrieval_hit_rate",
        "mean_reciprocal_rank",
        "answer_pass_rate",
    ],
)
def test_each_supported_metric_can_independently_fail_a_configured_gate(metric):
    baseline_summary = _summary().model_copy(update={metric: 0.8})
    current_summary = _summary().model_copy(update={metric: 0.7})
    result = compare_evaluation_runs(
        baseline=_run("baseline", summary=baseline_summary),
        current=_run("current", summary=current_summary),
        policy=EvaluationRegressionPolicy(
            metric_thresholds={metric: MetricRegressionThreshold(maximum_absolute_drop=0.05)}
        ),
    )

    assert _metric(result, metric).regressed
    assert result.regression_reasons == ["metric_threshold_breached"]


def test_compatibility_rules_are_structured_and_policy_controlled():
    baseline = _run("baseline")
    assert validate_run_compatibility(baseline=baseline, current=_run("current")).compatible

    version_drift = validate_run_compatibility(
        baseline=baseline,
        current=_run("current", dataset_version="2026.08"),
    )
    assert version_drift.compatible
    assert version_drift.warnings == ["dataset_version_differs"]

    incompatible = validate_run_compatibility(
        baseline=baseline,
        current=_run("current", dataset_name="other", retrieval_k=10),
    )
    assert not incompatible.compatible
    assert incompatible.errors == ["dataset_name_differs", "retrieval_k_differs"]

    allowed = validate_run_compatibility(
        baseline=baseline,
        current=_run(
            "current",
            dataset_name="other",
            dataset_version="2026.08",
            retrieval_k=10,
        ),
        policy=EvaluationRegressionPolicy(
            require_same_dataset_name=False,
            require_same_retrieval_k=False,
        ),
    )
    assert allowed.compatible
    assert allowed.warnings == [
        "dataset_name_differs",
        "dataset_version_differs",
        "retrieval_k_differs",
    ]

    strict_version = validate_run_compatibility(
        baseline=baseline,
        current=_run("current", dataset_version="2026.08"),
        policy=EvaluationRegressionPolicy(require_same_dataset_version=True),
    )
    assert strict_version.errors == ["dataset_version_differs"]


def test_transient_missing_summary_schema_and_semantic_option_differences_are_checked():
    baseline = _run("baseline")
    transient = validate_run_compatibility(
        baseline=baseline,
        current=_run("current", status=EvaluationRunStatus.RUNNING),
    )
    assert transient.errors == ["current_run_not_terminal"]

    no_summary = validate_run_compatibility(
        baseline=baseline,
        current=_run("current").model_copy(update={"summary": None}),
    )
    assert no_summary.errors == ["current_summary_missing"]

    schema = validate_run_compatibility(
        baseline=baseline,
        current=_run("current", schema_version="2.0"),
    )
    assert schema.errors == ["report_schema_version_differs"]

    failed = validate_run_compatibility(
        baseline=_run("baseline", status=EvaluationRunStatus.FAILED),
        current=_run("current", status=EvaluationRunStatus.FAILED),
    )
    assert failed.compatible
    assert failed.warnings == ["baseline_run_failed", "current_run_failed"]

    changed_config = deepcopy(baseline.configuration)
    changed_config["require_all_expected_sources"] = False
    option_result = validate_run_compatibility(
        baseline=baseline,
        current=_run("current", configuration=changed_config),
    )
    assert option_result.compatible
    assert option_result.warnings == ["evaluation_configuration_differs"]

    pending_case = validate_run_compatibility(
        baseline=baseline,
        current=_run(
            "current",
            results=[_case("case", EvaluationCaseStatus.PENDING)],
        ),
    )
    assert pending_case.errors == ["current_case_status_not_terminal"]


def test_duplicate_case_ids_make_comparison_incompatible_without_selecting_a_result():
    duplicate = _case("duplicate", EvaluationCaseStatus.PASSED)
    baseline = _run("baseline").model_copy(update={"results": [duplicate, duplicate]})
    current = _run("current").model_copy(update={"results": [duplicate]})

    baseline_result = compare_evaluation_runs(baseline=baseline, current=current)
    current_result = compare_evaluation_runs(
        baseline=current,
        current=current.model_copy(update={"results": [duplicate, duplicate]}),
    )

    assert not baseline_result.compatible
    assert baseline_result.compatibility_errors == ["duplicate_baseline_case_id"]
    assert baseline_result.case_results == []
    assert current_result.compatibility_errors == ["duplicate_current_case_id"]


@pytest.mark.parametrize(
    ("baseline_status", "current_status", "transition", "regressed", "improved"),
    [
        ("passed", "passed", "unchanged_pass", False, False),
        ("passed", "failed", "pass_to_fail", True, False),
        ("passed", "error", "pass_to_error", True, False),
        ("passed", "skipped", "pass_to_skip", True, False),
        ("failed", "passed", "fail_to_pass", False, True),
        ("failed", "failed", "unchanged_fail", False, False),
        ("failed", "error", "fail_to_error", True, False),
        ("failed", "skipped", "fail_to_skip", False, False),
        ("error", "passed", "error_to_pass", False, True),
        ("error", "failed", "error_to_fail", False, True),
        ("error", "error", "unchanged_error", False, False),
        ("error", "skipped", "error_to_skip", False, False),
        ("skipped", "passed", "skip_to_pass", False, True),
        ("skipped", "failed", "skip_to_fail", True, False),
        ("skipped", "error", "skip_to_error", True, False),
        ("skipped", "skipped", "unchanged_skip", False, False),
    ],
)
def test_every_case_status_transition_is_explicit(
    baseline_status, current_status, transition, regressed, improved
):
    baseline_enum = EvaluationCaseStatus(baseline_status)
    current_enum = EvaluationCaseStatus(current_status)
    result = compare_evaluation_runs(
        baseline=_run(
            "baseline",
            results=[
                _case(
                    "case",
                    baseline_enum,
                    error="baseline error" if baseline_enum is EvaluationCaseStatus.ERROR else None,
                )
            ],
            summary=_summary(),
        ),
        current=_run(
            "current",
            results=[
                _case(
                    "case",
                    current_enum,
                    error="current error" if current_enum is EvaluationCaseStatus.ERROR else None,
                )
            ],
            summary=_summary(),
        ),
    )

    case = result.case_results[0]
    assert case.transition is CaseStatusTransition(transition)
    assert case.regressed is regressed
    assert case.improved is improved


def test_case_collections_diagnostics_order_and_default_regression_decision():
    baseline = _run(
        "baseline",
        results=[
            _case("same", EvaluationCaseStatus.PASSED),
            _case("new-fail", EvaluationCaseStatus.PASSED, answer_reasons=["old"]),
            _case("new-error", EvaluationCaseStatus.FAILED),
            _case("recovered", EvaluationCaseStatus.FAILED, retrieval_reasons=["missing"]),
            _case("removed", EvaluationCaseStatus.PASSED),
        ],
        summary=_summary(total_cases=5),
    )
    current = _run(
        "current",
        results=[
            _case("same", EvaluationCaseStatus.PASSED),
            _case("new-fail", EvaluationCaseStatus.FAILED, answer_reasons=["bad-answer"]),
            _case("new-error", EvaluationCaseStatus.ERROR, error="safe current error"),
            _case("recovered", EvaluationCaseStatus.PASSED),
            _case("added-pass", EvaluationCaseStatus.PASSED),
        ],
        summary=_summary(total_cases=5),
    )

    result = compare_evaluation_runs(baseline=baseline, current=current)

    assert [item.case_id for item in result.case_results] == [
        "same",
        "new-fail",
        "new-error",
        "recovered",
        "added-pass",
        "removed",
    ]
    assert result.newly_failed_case_ids == ["new-fail"]
    assert result.newly_errored_case_ids == ["new-error"]
    assert result.recovered_case_ids == ["recovered"]
    assert result.added_case_ids == ["added-pass"]
    assert result.removed_case_ids == ["removed"]
    assert result.regressed
    assert result.regression_reasons == ["new_failed_case", "new_error_case"]
    assert result.compared_case_count == 4
    assert result.newly_failed_case_count == 1
    assert result.newly_errored_case_count == 1
    assert result.recovered_case_count == 1
    assert _case_result(result, "new-fail").baseline_failure_reasons == ["old"]
    assert _case_result(result, "new-fail").current_failure_reasons == ["bad-answer"]
    assert _case_result(result, "new-error").current_failure_reasons == ["safe current error"]
    assert "not exposed" not in result.model_dump_json()


@pytest.mark.parametrize(
    ("status", "expected_reason"),
    [
        (EvaluationCaseStatus.PASSED, None),
        (EvaluationCaseStatus.SKIPPED, None),
        (EvaluationCaseStatus.FAILED, "added_failing_case"),
        (EvaluationCaseStatus.ERROR, "added_error_case"),
    ],
)
def test_added_non_passing_cases_fail_by_default_but_other_added_cases_do_not(
    status, expected_reason
):
    added = _case(
        "added",
        status,
        error="safe" if status is EvaluationCaseStatus.ERROR else None,
    )
    result = compare_evaluation_runs(
        baseline=_run("baseline", results=[_case("same", EvaluationCaseStatus.PASSED)]),
        current=_run("current", results=[_case("same", EvaluationCaseStatus.PASSED), added]),
    )

    assert result.regressed is (expected_reason is not None)
    assert result.regression_reasons == ([expected_reason] if expected_reason else [])


def test_strict_added_removed_policies_and_allow_new_case_regressions():
    baseline = _run(
        "baseline",
        results=[
            _case("changed", EvaluationCaseStatus.PASSED),
            _case("removed", EvaluationCaseStatus.PASSED),
        ],
    )
    current = _run(
        "current",
        results=[
            _case("changed", EvaluationCaseStatus.ERROR, error="safe"),
            _case("added", EvaluationCaseStatus.PASSED),
        ],
    )
    allowed = compare_evaluation_runs(
        baseline=baseline,
        current=current,
        policy=EvaluationRegressionPolicy(
            fail_on_new_failed_cases=False,
            fail_on_new_error_cases=False,
        ),
    )
    strict = compare_evaluation_runs(
        baseline=baseline,
        current=current,
        policy=EvaluationRegressionPolicy(
            fail_on_new_error_cases=False,
            fail_on_added_cases=True,
            fail_on_removed_cases=True,
        ),
    )

    assert not allowed.regressed
    assert strict.regression_reasons == ["added_case", "removed_case"]


def test_incompatible_runs_are_not_labelled_as_quality_regressions():
    result = compare_evaluation_runs(
        baseline=_run("baseline"),
        current=_run("current", dataset_name="other"),
    )

    assert not result.compatible
    assert not result.regressed
    assert result.regression_reasons == []
    assert result.metric_results == []
    assert result.case_results == []


def test_comparison_is_deterministic_and_does_not_mutate_inputs():
    baseline = _run("baseline")
    current = _run("current")
    policy = EvaluationRegressionPolicy(
        metric_thresholds={
            "retrieval_recall_at_k": MetricRegressionThreshold(maximum_absolute_drop=0.01)
        }
    )
    before = (
        baseline.model_dump(mode="json"),
        current.model_dump(mode="json"),
        policy.model_dump(mode="json"),
    )

    first = compare_evaluation_runs(baseline=baseline, current=current, policy=policy)
    second = compare_evaluation_runs(baseline=baseline, current=current, policy=policy)

    assert first == second
    assert before == (
        baseline.model_dump(mode="json"),
        current.model_dump(mode="json"),
        policy.model_dump(mode="json"),
    )


def test_file_helper_uses_persisted_reports_without_modifying_them(tmp_path):
    baseline_path = tmp_path / "baseline.json"
    current_path = tmp_path / "current.json"
    save_evaluation_report(_run("baseline"), baseline_path)
    save_evaluation_report(_run("current"), current_path)
    before = (baseline_path.read_bytes(), current_path.read_bytes())

    result = compare_evaluation_report_files(
        baseline_path=baseline_path,
        current_path=current_path,
    )

    assert result.compatible
    assert before == (baseline_path.read_bytes(), current_path.read_bytes())
