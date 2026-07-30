from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import cast

import pytest
from pydantic import ValidationError

from assistant.domain import KnowledgeChunk, KnowledgeDocument
from assistant.evaluation import (
    AnswerEvaluationOptions,
    EvaluationCase,
    EvaluationCaseStatus,
    EvaluationDataset,
    EvaluationRunner,
    EvaluationRunOptions,
    EvaluationRunStatus,
)
from assistant.schemas import ChatResponse, SourceReference


def chunk(
    chunk_id: str,
    document_id: str,
    *,
    content: str = "Useful context",
    score: float = 0.9,
) -> KnowledgeChunk:
    return KnowledgeChunk(
        id=chunk_id,
        document=KnowledgeDocument(id=document_id, title=f"Title {document_id}"),
        content=content,
        score=score,
    )


def case(
    case_id: str,
    *,
    sources: list[str] | None = None,
    contains: list[str] | None = None,
    excludes: list[str] | None = None,
) -> EvaluationCase:
    return EvaluationCase(
        id=case_id,
        question=f"Question {case_id}?",
        expected_source_ids=sources or [],
        expected_answer_contains=contains or [],
        expected_answer_excludes=excludes or [],
    )


class FixedClock:
    def __init__(self, *values: datetime) -> None:
        self.values = iter(values)

    def now(self) -> datetime:
        return next(self.values)


class FakeRetrievalService:
    def __init__(self, results: dict[str, list[KnowledgeChunk] | Exception]) -> None:
        self.results = results
        self.calls: list[str] = []

    def retrieve(self, query: str) -> list[KnowledgeChunk]:
        self.calls.append(query)
        result = self.results[query]
        if isinstance(result, Exception):
            raise result
        return result


class FakeAnswerService:
    def __init__(self, responses: dict[str, ChatResponse | Exception]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, list[KnowledgeChunk]]] = []

    def generate(self, *, question: str, retrieved_context: list[KnowledgeChunk]) -> ChatResponse:
        self.calls.append((question, list(retrieved_context)))
        response = self.responses[question]
        if isinstance(response, Exception):
            raise response
        return response


def response(message: str, *source_ids: str) -> ChatResponse:
    return ChatResponse(
        message=message,
        sources=[SourceReference(id=value, title=f"Title {value}") for value in source_ids],
    )


def runner(
    retrieval: FakeRetrievalService,
    answers: FakeAnswerService,
    *clock_values: datetime,
) -> EvaluationRunner:
    return EvaluationRunner(
        retrieval_service=retrieval,
        answer_service=answers,
        clock=FixedClock(*clock_values),
        id_generator=lambda: "fixed-run-id",
    )


def test_run_case_executes_services_and_real_evaluators_without_mutating_inputs():
    evaluation_case = case("case-1", sources=["doc-1"], contains=["aligned"])
    retrieved = [chunk("chunk-1", "doc-1", content="Workshops align teams")]
    retrieval = FakeRetrievalService({evaluation_case.question: retrieved})
    answers = FakeAnswerService({evaluation_case.question: response("Teams are aligned.", "doc-1")})
    before = deepcopy((evaluation_case, retrieved))
    started = datetime(2026, 7, 30, 9, 0, tzinfo=timezone.utc)

    result = runner(
        retrieval,
        answers,
        started,
        started + timedelta(milliseconds=25),
    ).run_case(evaluation_case)

    assert result.status is EvaluationCaseStatus.PASSED
    assert result.error is None
    assert result.retrieval is not None
    assert result.retrieval.recall_at_k == 1.0
    assert result.answer is not None
    assert result.answer.passed is True
    assert result.started_at == started
    assert result.completed_at == started + timedelta(milliseconds=25)
    assert result.duration_ms == 25.0
    assert retrieval.calls == [evaluation_case.question]
    assert answers.calls == [(evaluation_case.question, retrieved)]
    assert (evaluation_case, retrieved) == before


@pytest.mark.parametrize(
    ("retrieved", "answer", "expected_retrieval", "expected_answer"),
    [
        ([], response("Expected text", "doc-1"), 0.0, False),
        ([chunk("one", "doc-1")], response("Wrong text", "doc-1"), 0.5, False),
    ],
)
def test_deterministic_check_failures_are_failed_not_errors(
    retrieved: list[KnowledgeChunk],
    answer: ChatResponse,
    expected_retrieval: float,
    expected_answer: bool,
):
    evaluation_case = case("case-1", sources=["doc-1", "doc-2"], contains=["Expected text"])
    retrieval = FakeRetrievalService({evaluation_case.question: retrieved})
    answers = FakeAnswerService({evaluation_case.question: answer})
    started = datetime(2026, 7, 30, tzinfo=timezone.utc)

    result = runner(retrieval, answers, started, started).run_case(evaluation_case)

    assert result.status is EvaluationCaseStatus.FAILED
    assert result.error is None
    assert result.retrieval is not None
    assert result.retrieval.recall_at_k == expected_retrieval
    assert result.answer is not None
    assert result.answer.passed is expected_answer


def test_partial_recall_can_be_accepted_explicitly():
    evaluation_case = case("case-1", sources=["doc-1", "doc-2"])
    retrieved = [chunk("one", "doc-1")]
    retrieval = FakeRetrievalService({evaluation_case.question: retrieved})
    answers = FakeAnswerService({evaluation_case.question: response("Answer", "doc-1")})
    now = datetime(2026, 7, 30, tzinfo=timezone.utc)

    result = runner(retrieval, answers, now, now).run_case(
        evaluation_case,
        options=EvaluationRunOptions(require_all_expected_sources=False),
    )

    assert result.status is EvaluationCaseStatus.PASSED


@pytest.mark.parametrize(
    ("evaluation_case", "generated"),
    [
        (case("excluded", excludes=["never"]), response("Never do this")),
        (case("uncited", sources=["doc-1"]), response("Answer without a citation")),
        (case("invented", sources=["doc-1"]), response("Answer", "doc-2")),
    ],
)
def test_answer_check_failures_compose_to_failed_cases(
    evaluation_case: EvaluationCase,
    generated: ChatResponse,
):
    retrieval = FakeRetrievalService({evaluation_case.question: [chunk("chunk-1", "doc-1")]})
    answers = FakeAnswerService({evaluation_case.question: generated})
    now = datetime(2026, 7, 30, tzinfo=timezone.utc)

    result = runner(retrieval, answers, now, now).run_case(evaluation_case)

    assert result.status is EvaluationCaseStatus.FAILED
    assert result.error is None
    assert result.answer is not None and result.answer.passed is False


def test_unevaluable_cases_are_skipped_but_one_applicable_stage_can_pass():
    no_expectations = case("none")
    answer_only = case("answer", contains=["yes"])
    retrieval = FakeRetrievalService(
        {
            no_expectations.question: [],
            answer_only.question: [],
        }
    )
    answers = FakeAnswerService(
        {
            no_expectations.question: response("Anything"),
            answer_only.question: response("Yes"),
        }
    )
    now = datetime(2026, 7, 30, tzinfo=timezone.utc)
    evaluation_runner = runner(retrieval, answers, now, now, now, now)

    skipped = evaluation_runner.run_case(no_expectations)
    passed = evaluation_runner.run_case(answer_only)

    assert skipped.status is EvaluationCaseStatus.SKIPPED
    assert skipped.metadata["diagnostic_reasons"] == ["no_evaluable_expectations"]
    assert passed.status is EvaluationCaseStatus.PASSED
    assert passed.retrieval is not None and passed.retrieval.hit is None


def test_unevaluable_answer_does_not_override_passing_retrieval():
    evaluation_case = case("retrieval", sources=["doc-1"])
    retrieval = FakeRetrievalService({evaluation_case.question: [chunk("chunk-1", "doc-1")]})
    answers = FakeAnswerService({evaluation_case.question: response("Any answer")})
    now = datetime(2026, 7, 30, tzinfo=timezone.utc)

    result = runner(retrieval, answers, now, now).run_case(
        evaluation_case,
        options=EvaluationRunOptions(
            answer_options=AnswerEvaluationOptions(require_citations_when_sources_expected=False)
        ),
    )

    assert result.status is EvaluationCaseStatus.PASSED
    assert result.answer is not None and result.answer.passed is None


def test_retrieval_error_is_safe_and_does_not_call_answer_service():
    evaluation_case = case("case-1", contains=["answer"])
    retrieval = FakeRetrievalService({evaluation_case.question: RuntimeError("token=top-secret")})
    answers = FakeAnswerService({evaluation_case.question: response("answer")})
    now = datetime(2026, 7, 30, tzinfo=timezone.utc)

    result = runner(retrieval, answers, now, now).run_case(evaluation_case)

    assert result.status is EvaluationCaseStatus.ERROR
    assert result.error == "evaluation case failed (RuntimeError)"
    assert "secret" not in result.error
    assert result.duration_ms == 0.0
    assert answers.calls == []


def test_answer_error_retains_retrieval_result():
    evaluation_case = case("case-1", sources=["doc-1"])
    retrieval = FakeRetrievalService({evaluation_case.question: [chunk("chunk-1", "doc-1")]})
    answers = FakeAnswerService({evaluation_case.question: RuntimeError("provider failed")})
    now = datetime(2026, 7, 30, tzinfo=timezone.utc)

    result = runner(retrieval, answers, now, now).run_case(evaluation_case)

    assert result.status is EvaluationCaseStatus.ERROR
    assert result.retrieval is not None
    assert result.retrieval.hit is True
    assert result.answer is None


@pytest.mark.parametrize("malformed_stage", ["retrieval", "answer"])
def test_malformed_service_responses_are_isolated_as_adapter_errors(malformed_stage: str):
    evaluation_case = case("case-1", contains=["answer"])
    retrieval_result: list[KnowledgeChunk] = (
        cast(list[KnowledgeChunk], ["not-a-knowledge-chunk"])
        if malformed_stage == "retrieval"
        else [chunk("chunk-1", "doc-1")]
    )
    retrieval = FakeRetrievalService({evaluation_case.question: retrieval_result})
    answer_result: ChatResponse = (
        cast(ChatResponse, {"message": "answer"})
        if malformed_stage == "answer"
        else response("answer")
    )
    answers = FakeAnswerService({evaluation_case.question: answer_result})
    now = datetime(2026, 7, 30, tzinfo=timezone.utc)

    result = runner(retrieval, answers, now, now).run_case(evaluation_case)

    assert result.status is EvaluationCaseStatus.ERROR
    assert result.error == "evaluation case failed (AttributeError)"


def test_run_dataset_preserves_order_isolates_errors_and_builds_summary():
    cases = [
        case("passed", sources=["doc-1"], contains=["yes"]),
        case("failed", contains=["required"]),
        case("errored", contains=["answer"]),
        case("skipped"),
    ]
    dataset = EvaluationDataset(name="suite", version="v1", cases=cases, metadata={"team": "qa"})
    retrieval = FakeRetrievalService(
        {
            cases[0].question: [chunk("one", "doc-1")],
            cases[1].question: [],
            cases[2].question: RuntimeError("unavailable"),
            cases[3].question: [],
        }
    )
    answers = FakeAnswerService(
        {
            cases[0].question: response("Yes", "doc-1"),
            cases[1].question: response("No"),
            cases[3].question: response("No expectations"),
        }
    )
    before = deepcopy(dataset)
    start = datetime(2026, 7, 30, 10, 0, tzinfo=timezone.utc)
    times = [
        start + timedelta(milliseconds=value) for value in (0, 10, 20, 30, 50, 60, 70, 80, 80, 100)
    ]

    run = runner(retrieval, answers, *times).run_dataset(
        dataset,
        options=EvaluationRunOptions(
            retrieval_k=1,
            metadata={"purpose": "regression"},
        ),
    )

    assert run.id == "fixed-run-id"
    assert run.status is EvaluationRunStatus.COMPLETED
    assert [result.case_id for result in run.results] == [value.id for value in cases]
    assert [result.status for result in run.results] == [
        EvaluationCaseStatus.PASSED,
        EvaluationCaseStatus.FAILED,
        EvaluationCaseStatus.ERROR,
        EvaluationCaseStatus.SKIPPED,
    ]
    assert run.started_at == start
    assert run.completed_at == start + timedelta(milliseconds=100)
    assert run.summary is not None
    assert run.summary.model_dump() == {
        "total_cases": 4,
        "passed_cases": 1,
        "failed_cases": 1,
        "error_cases": 1,
        "skipped_cases": 1,
        "retrieval_precision_at_k": 1.0,
        "retrieval_recall_at_k": 1.0,
        "retrieval_hit_rate": 1.0,
        "mean_reciprocal_rank": 1.0,
        "answer_pass_rate": 0.5,
        "average_duration_ms": 10.0,
    }
    assert run.configuration["retrieval_k"] == 1
    assert run.configuration["continue_on_error"] is True
    assert run.configuration["answer_evaluation"]["case_sensitive"] is False
    assert run.metadata == {"purpose": "regression"}
    assert dataset == before
    assert retrieval.calls == [value.question for value in cases]


def test_continue_on_error_false_returns_failed_partial_run():
    cases = [case("error"), case("not-run")]
    dataset = EvaluationDataset(name="suite", version="v1", cases=cases)
    retrieval = FakeRetrievalService(
        {
            cases[0].question: RuntimeError("unavailable"),
            cases[1].question: [],
        }
    )
    answers = FakeAnswerService({})
    now = datetime(2026, 7, 30, tzinfo=timezone.utc)

    run = runner(retrieval, answers, now, now, now, now).run_dataset(
        dataset,
        options=EvaluationRunOptions(continue_on_error=False),
    )

    assert run.status is EvaluationRunStatus.FAILED
    assert [result.case_id for result in run.results] == ["error"]
    assert run.summary is not None
    assert run.summary.total_cases == 2
    assert run.summary.error_cases == 1
    assert retrieval.calls == [cases[0].question]


def test_retrieval_k_only_limits_evaluation_and_content_is_excluded_by_default():
    evaluation_case = case("case-1", sources=["doc-1"])
    retrieved = [chunk("one", "doc-1"), chunk("two", "doc-2")]
    retrieval = FakeRetrievalService({evaluation_case.question: retrieved})
    answers = FakeAnswerService({evaluation_case.question: response("Answer", "doc-1")})
    now = datetime(2026, 7, 30, tzinfo=timezone.utc)

    result = runner(retrieval, answers, now, now).run_case(
        evaluation_case,
        options=EvaluationRunOptions(retrieval_k=1),
    )

    assert answers.calls == [(evaluation_case.question, retrieved)]
    assert result.retrieval is not None
    assert len(result.retrieval.retrieved_items) == 1
    assert result.retrieval.retrieved_items[0].content is None


def test_options_are_frozen_serializable_and_validate_retrieval_k():
    options = EvaluationRunOptions(
        answer_options=AnswerEvaluationOptions(case_sensitive=True),
        metadata={"label": "safe"},
    )

    assert options.model_dump(mode="json")["answer_options"]["case_sensitive"] is True
    with pytest.raises(ValidationError, match="retrieval_k"):
        EvaluationRunOptions(retrieval_k=0)
    with pytest.raises(ValidationError):
        options.continue_on_error = False  # type: ignore[misc]


def test_include_retrieved_content_is_explicit():
    evaluation_case = case("case-1", contains=["answer"])
    retrieval = FakeRetrievalService(
        {evaluation_case.question: [chunk("one", "doc-1", content="Sensitive context")]}
    )
    answers = FakeAnswerService({evaluation_case.question: response("answer")})
    now = datetime(2026, 7, 30, tzinfo=timezone.utc)

    result = runner(retrieval, answers, now, now).run_case(
        evaluation_case,
        options=EvaluationRunOptions(include_retrieved_content=True),
    )

    assert result.retrieval is not None
    assert result.retrieval.retrieved_items[0].content == "Sensitive context"


def test_run_id_is_generated_once_and_default_clock_is_utc_aware():
    evaluation_case = case("case-1")
    dataset = EvaluationDataset(name="suite", version="v1", cases=[evaluation_case])
    retrieval = FakeRetrievalService({evaluation_case.question: []})
    answers = FakeAnswerService({evaluation_case.question: response("answer")})
    generated_ids: list[str] = []

    def generate_id() -> str:
        generated_ids.append("run-1")
        return "run-1"

    run = EvaluationRunner(
        retrieval_service=retrieval,
        answer_service=answers,
        id_generator=generate_id,
    ).run_dataset(dataset)

    assert run.id == "run-1"
    assert generated_ids == ["run-1"]
    assert run.started_at is not None and run.started_at.utcoffset() == timedelta(0)
    assert run.completed_at is not None and run.completed_at.utcoffset() == timedelta(0)
