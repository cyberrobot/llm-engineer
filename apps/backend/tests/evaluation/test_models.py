from datetime import datetime, timedelta, timezone
from math import inf, nan

import pytest
from pydantic import ValidationError

from assistant.evaluation import (
    AnswerEvaluationOptions,
    AnswerEvaluationResult,
    AnswerEvaluationSummary,
    EvaluationCase,
    EvaluationCaseResult,
    EvaluationCaseStatus,
    EvaluationDataset,
    EvaluationRun,
    EvaluationRunStatus,
    EvaluationSummary,
    RetrievalEvaluationResult,
    RetrievalEvaluationSummary,
    RetrievedItem,
)

UTC_START = datetime(2026, 7, 29, 9, 0, tzinfo=timezone.utc)


def test_evaluation_case_accepts_minimal_input_and_uses_independent_defaults():
    first = EvaluationCase(id="case-1", question="What is discovery?")
    second = EvaluationCase(id="case-2", question="Why run discovery?")

    first.tags.append("core")
    first.metadata["priority"] = 1

    assert first.expected_source_ids == []
    assert second.tags == []
    assert second.metadata == {}


def test_evaluation_case_accepts_full_input_and_normalizes_human_entered_values():
    case = EvaluationCase(
        id="  case-1  ",
        question="  What is discovery?  ",
        description="  A core question  ",
        expected_source_ids=[" source-A ", "source-A", "source-B"],
        expected_answer_contains=[" workshops ", "workshops", "alignment"],
        expected_answer_excludes=["guaranteed", " guaranteed "],
        tags=[" core ", "core", "smoke"],
        metadata={"original_label": " Keep My Case ", "nested": {"values": [1, True, None]}},
    )

    assert case.id == "case-1"
    assert case.question == "What is discovery?"
    assert case.description == "A core question"
    assert case.expected_source_ids == ["source-A", "source-B"]
    assert case.expected_answer_contains == ["workshops", "alignment"]
    assert case.expected_answer_excludes == ["guaranteed"]
    assert case.tags == ["core", "smoke"]
    assert case.metadata["original_label"] == " Keep My Case "


@pytest.mark.parametrize(("field", "value"), [("id", ""), ("id", "  "), ("question", "\n")])
def test_evaluation_case_rejects_empty_required_strings(field, value):
    values = {"id": "case-1", "question": "Question", field: value}

    with pytest.raises(ValidationError, match=field):
        EvaluationCase.model_validate(values)


@pytest.mark.parametrize(
    "field",
    [
        "expected_source_ids",
        "expected_answer_contains",
        "expected_answer_excludes",
        "tags",
    ],
)
def test_evaluation_case_rejects_empty_collection_elements(field):
    with pytest.raises(ValidationError, match=field):
        EvaluationCase.model_validate({"id": "case-1", "question": "Question", field: [" "]})


def test_evaluation_dataset_accepts_valid_cases_and_aware_created_at():
    dataset = EvaluationDataset(
        name="  discovery  ",
        version="  2026.07  ",
        cases=[EvaluationCase(id="case-1", question="Question")],
        description="  Regression set  ",
        created_at=UTC_START,
        tags=[" release ", "release"],
    )

    assert dataset.name == "discovery"
    assert dataset.version == "2026.07"
    assert dataset.description == "Regression set"
    assert dataset.created_at == UTC_START
    assert dataset.tags == ["release"]


def test_evaluation_dataset_defaults_to_schema_version_1_for_python_callers():
    dataset = EvaluationDataset(
        name="discovery",
        version="2026.07",
        cases=[EvaluationCase(id="case-1", question="Question")],
    )

    assert dataset.schema_version == "1.0"


def test_evaluation_dataset_accepts_an_explicit_schema_version():
    dataset = EvaluationDataset(
        schema_version=" 1.0 ",
        name="discovery",
        version="2026.07",
        cases=[EvaluationCase(id="case-1", question="Question")],
    )

    assert dataset.schema_version == "1.0"


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"cases": []}, "cases"),
        ({"name": " "}, "name"),
        ({"version": ""}, "version"),
        ({"created_at": datetime(2026, 7, 29, 9, 0)}, "created_at"),
    ],
)
def test_evaluation_dataset_rejects_invalid_structure(overrides, field):
    values = {
        "name": "dataset",
        "version": "1",
        "cases": [EvaluationCase(id="case-1", question="Question")],
        **overrides,
    }

    with pytest.raises(ValidationError, match=field):
        EvaluationDataset.model_validate(values)


def test_evaluation_dataset_rejects_duplicate_case_ids():
    with pytest.raises(ValidationError, match="unique"):
        EvaluationDataset(
            name="dataset",
            version="1",
            cases=[
                EvaluationCase(id="same", question="First"),
                EvaluationCase(id="same", question="Second"),
            ],
        )


def test_retrieved_item_accepts_minimal_and_full_records():
    minimal = RetrievedItem(id=" item-1 ", rank=1)
    full = RetrievedItem(
        id="item-2",
        rank=2,
        document_id=" document-1 ",
        chunk_id=" chunk-2 ",
        content="  Content is preserved.  ",
        score=12.5,
        distance=-3.0,
        metadata={"source": " Internal "},
    )

    assert minimal.id == "item-1"
    assert full.document_id == "document-1"
    assert full.chunk_id == "chunk-2"
    assert full.content == "  Content is preserved.  "
    assert full.score == 12.5
    assert full.distance == -3.0
    assert full.metadata == {"source": " Internal "}


@pytest.mark.parametrize("rank", [0, -1])
def test_retrieved_item_rejects_rank_below_one(rank):
    with pytest.raises(ValidationError, match="rank"):
        RetrievedItem(id="item", rank=rank)


@pytest.mark.parametrize(("field", "value"), [("score", inf), ("score", nan), ("distance", inf)])
def test_retrieved_item_rejects_non_finite_numbers(field, value):
    with pytest.raises(ValidationError, match=field):
        RetrievedItem.model_validate({"id": "item", "rank": 1, field: value})


def test_retrieval_result_accepts_empty_result_with_unset_metrics():
    result = RetrievalEvaluationResult(retrieved_items=[])

    assert result.precision_at_k is None
    assert result.recall_at_k is None
    assert result.reciprocal_rank is None
    assert result.hit is None
    assert result.unmatched_expected_source_ids == []
    assert result.unexpected_retrieved_source_ids == []
    assert result.duplicate_retrieved_source_ids == []
    assert result.evaluated_at_k is None


def test_retrieval_summary_accepts_defined_empty_aggregate():
    summary = RetrievalEvaluationSummary(
        evaluated_cases=0,
        source_evaluable_cases=0,
        average_retrieved_items=0.0,
    )

    assert summary.precision_at_k is None
    assert summary.recall_at_k is None
    assert summary.hit_rate is None
    assert summary.mean_reciprocal_rank is None


def test_retrieval_summary_rejects_more_evaluable_cases_than_supplied_cases():
    with pytest.raises(ValidationError, match="Source-evaluable cases"):
        RetrievalEvaluationSummary(
            evaluated_cases=1,
            source_evaluable_cases=2,
            average_retrieved_items=0.0,
        )


def test_retrieval_result_accepts_populated_result():
    result = RetrievalEvaluationResult(
        retrieved_items=[RetrievedItem(id="one", rank=1), RetrievedItem(id="two", rank=2)],
        precision_at_k=0.5,
        recall_at_k=1.0,
        reciprocal_rank=1.0,
        hit=True,
        expected_source_ids=["source-1", "source-1"],
        matched_source_ids=["source-1"],
        failure_reasons=[" partial match ", "partial match"],
    )

    assert result.expected_source_ids == ["source-1"]
    assert result.failure_reasons == ["partial match"]


@pytest.mark.parametrize(
    "items",
    [
        [RetrievedItem(id="one", rank=1), RetrievedItem(id="two", rank=1)],
        [RetrievedItem(id="two", rank=2)],
        [RetrievedItem(id="two", rank=2), RetrievedItem(id="one", rank=1)],
        [RetrievedItem(id="one", rank=1), RetrievedItem(id="three", rank=3)],
    ],
)
def test_retrieval_result_rejects_duplicate_or_non_sequential_ranks(items):
    with pytest.raises(ValidationError, match="rank"):
        RetrievalEvaluationResult(retrieved_items=items)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("precision_at_k", -0.01),
        ("precision_at_k", 1.01),
        ("recall_at_k", -1),
        ("reciprocal_rank", 2),
    ],
)
def test_retrieval_result_rejects_metrics_outside_unit_interval(field, value):
    with pytest.raises(ValidationError, match=field):
        RetrievalEvaluationResult.model_validate({"retrieved_items": [], field: value})


def test_answer_result_accepts_empty_answer_and_unset_evaluation_fields():
    result = AnswerEvaluationResult(answer="")

    assert result.answer == ""
    assert result.passed is None
    assert result.citation_count is None
    assert result.citations_valid is None
    assert result.hallucination_detected is None


def test_answer_result_accepts_populated_output_and_zero_citations():
    result = AnswerEvaluationResult(
        answer="A grounded answer.",
        passed=True,
        matched_expected_fragments=[" grounded ", "grounded"],
        citation_count=0,
        citations_valid=True,
        hallucination_detected=False,
    )

    assert result.matched_expected_fragments == ["grounded"]
    assert result.citation_count == 0


def test_answer_result_source_diagnostics_are_serializable_and_have_independent_defaults():
    first = AnswerEvaluationResult(
        answer="Answer",
        cited_source_ids=[" doc-a ", "doc-a", "doc-b"],
        valid_citation_source_ids=["doc-a"],
        invalid_citation_source_ids=["doc-b"],
        duplicate_citation_source_ids=["doc-a"],
        cited_expected_source_ids=["doc-a"],
        cited_unexpected_source_ids=["doc-b"],
        uncited_expected_source_ids=["doc-c"],
    )
    second = AnswerEvaluationResult(answer="Other")
    restored = AnswerEvaluationResult.model_validate_json(first.model_dump_json())

    first.cited_source_ids.append("doc-c")

    assert restored.cited_source_ids == ["doc-a", "doc-b"]
    assert second.cited_source_ids == []


def test_answer_evaluation_options_are_immutable_and_forbid_unknown_configuration():
    options = AnswerEvaluationOptions()

    assert options.case_sensitive is False
    assert options.normalise_whitespace is True
    assert options.require_all_expected_fragments is True
    assert options.require_citations_when_sources_expected is True
    assert options.validate_citations_against_retrieval is True

    with pytest.raises(ValidationError, match="frozen"):
        options.case_sensitive = True
    with pytest.raises(ValidationError, match="extra"):
        AnswerEvaluationOptions.model_validate({"fuzzy_matching": True})


def test_answer_summary_validates_case_count_composition():
    summary = AnswerEvaluationSummary(
        evaluated_cases=3,
        evaluable_cases=2,
        passed_cases=1,
        failed_cases=1,
        unevaluable_cases=1,
        pass_rate=0.5,
        average_citation_count=1.0,
        citation_validity_rate=0.5,
    )

    assert AnswerEvaluationSummary.model_validate_json(summary.model_dump_json()) == summary

    with pytest.raises(ValidationError, match="counts"):
        AnswerEvaluationSummary(
            evaluated_cases=1,
            evaluable_cases=1,
            passed_cases=1,
            failed_cases=1,
            unevaluable_cases=0,
            pass_rate=1.0,
            average_citation_count=0.0,
        )


def test_answer_result_rejects_negative_citation_count():
    with pytest.raises(ValidationError, match="citation_count"):
        AnswerEvaluationResult(answer="Answer", citation_count=-1)


def test_answer_result_rejects_empty_failure_reason():
    with pytest.raises(ValidationError, match="failure_reasons"):
        AnswerEvaluationResult(answer="Answer", failure_reasons=[" "])


@pytest.mark.parametrize("status", list(EvaluationCaseStatus))
def test_case_status_values_serialize_as_stable_strings(status):
    result = EvaluationCaseResult(
        case_id="case-1",
        question="Question",
        status=status,
        error="execution failed" if status is EvaluationCaseStatus.ERROR else None,
    )

    assert result.model_dump(mode="json")["status"] == status.value
    assert f'"status":"{status.value}"' in result.model_dump_json()


def test_case_result_accepts_error_retrieval_only_and_answer_only_outputs():
    error = EvaluationCaseResult(
        case_id="error-case", question="Question", status="error", error="  provider timeout  "
    )
    retrieval_only = EvaluationCaseResult(
        case_id="retrieval-case",
        question="Question",
        status="passed",
        retrieval=RetrievalEvaluationResult(retrieved_items=[]),
    )
    answer_only = EvaluationCaseResult(
        case_id="answer-case",
        question="Question",
        status="failed",
        answer=AnswerEvaluationResult(answer="Answer", passed=False),
    )

    assert error.error == "provider timeout"
    assert retrieval_only.answer is None
    assert answer_only.retrieval is None


def test_error_case_result_requires_an_error_message():
    with pytest.raises(ValidationError, match="error"):
        EvaluationCaseResult(case_id="case-1", question="Question", status="error")


def test_case_result_rejects_negative_duration():
    with pytest.raises(ValidationError, match="duration_ms"):
        EvaluationCaseResult(
            case_id="case-1", question="Question", status="pending", duration_ms=-0.1
        )


def test_case_result_rejects_naive_or_reversed_timestamps():
    with pytest.raises(ValidationError, match="started_at"):
        EvaluationCaseResult(
            case_id="case-1",
            question="Question",
            status="pending",
            started_at=datetime(2026, 7, 29, 9, 0),
        )

    with pytest.raises(ValidationError, match="completed_at"):
        EvaluationCaseResult(
            case_id="case-1",
            question="Question",
            status="passed",
            started_at=UTC_START,
            completed_at=UTC_START - timedelta(seconds=1),
        )


def test_summary_accepts_in_progress_and_completed_counts():
    in_progress = EvaluationSummary(
        total_cases=3, passed_cases=1, failed_cases=0, error_cases=0, skipped_cases=0
    )
    complete = EvaluationSummary(
        total_cases=4,
        passed_cases=2,
        failed_cases=1,
        error_cases=1,
        skipped_cases=0,
        retrieval_precision_at_k=0.75,
        retrieval_recall_at_k=0.5,
        retrieval_hit_rate=1.0,
        mean_reciprocal_rank=0.875,
        answer_pass_rate=0.5,
        average_duration_ms=0,
    )

    assert in_progress.passed_cases == 1
    assert complete.average_duration_ms == 0


@pytest.mark.parametrize(
    "field", ["total_cases", "passed_cases", "failed_cases", "error_cases", "skipped_cases"]
)
def test_summary_rejects_negative_counts(field):
    values = {
        "total_cases": 1,
        "passed_cases": 0,
        "failed_cases": 0,
        "error_cases": 0,
        "skipped_cases": 0,
        field: -1,
    }

    with pytest.raises(ValidationError, match=field):
        EvaluationSummary.model_validate(values)


def test_summary_rejects_terminal_counts_exceeding_total():
    with pytest.raises(ValidationError, match="total_cases"):
        EvaluationSummary(
            total_cases=1, passed_cases=1, failed_cases=1, error_cases=0, skipped_cases=0
        )


@pytest.mark.parametrize(
    "field",
    [
        "retrieval_precision_at_k",
        "retrieval_recall_at_k",
        "retrieval_hit_rate",
        "mean_reciprocal_rank",
        "answer_pass_rate",
    ],
)
@pytest.mark.parametrize("value", [-0.01, 1.01])
def test_summary_rejects_ratios_outside_unit_interval(field, value):
    values = {
        "total_cases": 0,
        "passed_cases": 0,
        "failed_cases": 0,
        "error_cases": 0,
        "skipped_cases": 0,
        field: value,
    }

    with pytest.raises(ValidationError, match=field):
        EvaluationSummary.model_validate(values)


def test_evaluation_run_accepts_minimal_input_with_stable_defaults():
    run = EvaluationRun(
        id=" run-1 ",
        dataset_name=" dataset ",
        dataset_version=" 1 ",
        status=EvaluationRunStatus.PENDING,
        results=[],
    )

    assert run.id == "run-1"
    assert run.dataset_name == "dataset"
    assert run.dataset_version == "1"
    assert run.schema_version == "1.0"
    assert run.configuration == {}
    assert run.metadata == {}


def test_evaluation_run_accepts_complete_input():
    case_result = EvaluationCaseResult(
        case_id="case-1",
        question="Question",
        status=EvaluationCaseStatus.PASSED,
        started_at=UTC_START,
        completed_at=UTC_START + timedelta(seconds=1),
        duration_ms=1000,
    )
    summary = EvaluationSummary(
        total_cases=1, passed_cases=1, failed_cases=0, error_cases=0, skipped_cases=0
    )

    run = EvaluationRun(
        id="run-1",
        dataset_name="dataset",
        dataset_version="1",
        status=EvaluationRunStatus.COMPLETED,
        results=[case_result],
        started_at=UTC_START,
        completed_at=UTC_START + timedelta(seconds=1),
        summary=summary,
        configuration={"retrieval": {"k": 5}},
        metadata={"release": "8A"},
    )

    assert run.results == [case_result]
    assert run.summary == summary


def test_evaluation_run_rejects_duplicate_case_results():
    result = EvaluationCaseResult(case_id="case-1", question="Question", status="pending")

    with pytest.raises(ValidationError, match="unique"):
        EvaluationRun(
            id="run-1",
            dataset_name="dataset",
            dataset_version="1",
            status="running",
            results=[result, result.model_copy(update={"question": "Other"})],
        )


def test_evaluation_run_rejects_naive_or_reversed_timestamps():
    values = {
        "id": "run-1",
        "dataset_name": "dataset",
        "dataset_version": "1",
        "status": "running",
        "results": [],
    }

    with pytest.raises(ValidationError, match="started_at"):
        EvaluationRun.model_validate({**values, "started_at": datetime(2026, 7, 29, 9, 0)})

    with pytest.raises(ValidationError, match="completed_at"):
        EvaluationRun.model_validate(
            {
                **values,
                "started_at": UTC_START,
                "completed_at": UTC_START - timedelta(seconds=1),
            }
        )


@pytest.mark.parametrize("status", list(EvaluationRunStatus))
def test_run_status_values_serialize_as_stable_strings(status):
    run = EvaluationRun(
        id="run-1", dataset_name="dataset", dataset_version="1", status=status, results=[]
    )

    assert run.model_dump(mode="json")["status"] == status.value


@pytest.mark.parametrize(
    "model",
    [
        EvaluationCase(id="case-1", question="Question", metadata={"nested": [1, True, None]}),
        EvaluationDataset(
            name="dataset",
            version="1",
            cases=[EvaluationCase(id="case-1", question="Question")],
            created_at=UTC_START,
        ),
        RetrievedItem(id="item-1", rank=1, metadata={"nested": {"key": "value"}}),
        RetrievalEvaluationResult(retrieved_items=[RetrievedItem(id="item-1", rank=1)]),
        AnswerEvaluationResult(answer="Answer", metadata={"scores": [0.5, 1.0]}),
        EvaluationCaseResult(
            case_id="case-1", question="Question", status=EvaluationCaseStatus.PENDING
        ),
        EvaluationSummary(
            total_cases=1, passed_cases=0, failed_cases=0, error_cases=0, skipped_cases=0
        ),
        EvaluationRun(
            id="run-1",
            dataset_name="dataset",
            dataset_version="1",
            status=EvaluationRunStatus.PENDING,
            results=[],
            started_at=UTC_START,
            metadata={"nested": {"values": ["a", 2, False, None]}},
        ),
    ],
)
def test_public_models_round_trip_through_json(model):
    serialized = model.model_dump_json()
    reconstructed = type(model).model_validate_json(serialized)

    assert reconstructed == model


def test_json_serialization_uses_iso_datetimes_and_string_enums():
    run = EvaluationRun(
        id="run-1",
        dataset_name="dataset",
        dataset_version="1",
        status=EvaluationRunStatus.RUNNING,
        results=[],
        started_at=UTC_START,
    )

    serialized = run.model_dump(mode="json")

    assert serialized["status"] == "running"
    assert serialized["started_at"] == "2026-07-29T09:00:00Z"


@pytest.mark.parametrize(
    ("model_type", "values"),
    [
        (EvaluationCase, {"id": "case", "question": "Question"}),
        (RetrievedItem, {"id": "item", "rank": 1}),
        (
            EvaluationRun,
            {
                "id": "run",
                "dataset_name": "dataset",
                "dataset_version": "1",
                "status": "pending",
                "results": [],
            },
        ),
    ],
)
def test_public_models_reject_unexpected_fields(model_type, values):
    with pytest.raises(ValidationError, match="extra_forbidden"):
        model_type.model_validate({**values, "unexpected": "value"})


def test_metadata_rejects_values_that_are_not_json_compatible():
    with pytest.raises(ValidationError, match="metadata"):
        EvaluationCase(id="case", question="Question", metadata={"invalid": object()})
