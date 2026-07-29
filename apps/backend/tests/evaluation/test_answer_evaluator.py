from copy import deepcopy

import pytest

from assistant.domain import Citation
from assistant.evaluation import (
    AnswerEvaluationOptions,
    AnswerEvaluationResult,
    EvaluationCase,
    RetrievedItem,
    evaluate_answer,
    evaluate_chat_response,
    summarise_answer_results,
)
from assistant.schemas import ChatResponse, SourceReference


def case(
    *,
    contains: list[str] | None = None,
    excludes: list[str] | None = None,
    sources: list[str] | None = None,
) -> EvaluationCase:
    return EvaluationCase(
        id="password-reset",
        question="How do I reset my password?",
        expected_answer_contains=contains or [],
        expected_answer_excludes=excludes or [],
        expected_source_ids=sources or [],
    )


def citation(document_id: str, chunk_id: str = "chunk-1") -> Citation:
    return Citation(document_id=document_id, title="Guide", chunk_id=chunk_id)


def item(document_id: str | None, rank: int, chunk_id: str | None = None) -> RetrievedItem:
    return RetrievedItem(
        id=chunk_id or f"chunk-{rank}",
        document_id=document_id,
        chunk_id=chunk_id or f"chunk-{rank}",
        rank=rank,
    )


@pytest.mark.parametrize(
    ("answer", "fragment"),
    [
        ("reset link", "reset link"),
        ("Use the RESET LINK now.", "reset link"),
        ("  Use the reset   link now.  ", "reset link"),
        ("Use the reset link sent by email.", "reset link"),
        ("Код подтверждения отправлен", "код подтверждения"),
    ],
)
def test_default_matching_is_case_insensitive_whitespace_normalised_substring_matching(
    answer: str, fragment: str
):
    result = evaluate_answer(case=case(contains=[fragment]), answer=answer)

    assert result.passed is True
    assert result.matched_expected_fragments == [fragment]
    assert result.missing_expected_fragments == []


def test_case_sensitive_matching_and_punctuation_preservation_are_configurable_and_explicit():
    sensitive = evaluate_answer(
        case=case(contains=["Reset link"]),
        answer="Use the reset link.",
        options=AnswerEvaluationOptions(case_sensitive=True),
    )
    punctuation = evaluate_answer(
        case=case(contains=["reset-link"]),
        answer="Use the reset link.",
    )

    assert sensitive.passed is False
    assert sensitive.missing_expected_fragments == ["Reset link"]
    assert punctuation.passed is False


def test_whitespace_normalisation_can_be_disabled():
    result = evaluate_answer(
        case=case(contains=["reset link"]),
        answer="reset   link",
        options=AnswerEvaluationOptions(normalise_whitespace=False),
    )

    assert result.passed is False


def test_required_fragments_report_all_matches_and_misses_in_case_order():
    result = evaluate_answer(
        case=case(contains=["reset link", "registered email", "expires in an hour"]),
        answer="A RESET LINK is sent to your registered   email.",
    )

    assert result.passed is False
    assert result.matched_expected_fragments == ["reset link", "registered email"]
    assert result.missing_expected_fragments == ["expires in an hour"]
    assert result.failure_reasons == ["missing_expected_fragment"]


def test_any_required_fragment_option_passes_when_one_fragment_matches():
    result = evaluate_answer(
        case=case(contains=["reset link", "security code"]),
        answer="Use the reset link.",
        options=AnswerEvaluationOptions(require_all_expected_fragments=False),
    )

    assert result.passed is True
    assert result.missing_expected_fragments == ["security code"]
    assert result.failure_reasons == []


@pytest.mark.parametrize(
    "answer",
    [
        "Send us your PASSWORD.",
        "Send us your\n\npassword.",
        "Do not send us your password.",
    ],
)
def test_prohibited_fragments_fail_when_present_after_configured_normalisation(answer: str):
    result = evaluate_answer(
        case=case(excludes=["send us your password"]),
        answer=answer,
    )

    assert result.passed is False
    assert result.matched_excluded_fragments == ["send us your password"]
    assert result.failure_reasons == ["contains_excluded_fragment"]


def test_conflicting_include_and_exclude_expectations_fail_on_the_exclusion():
    result = evaluate_answer(
        case=case(contains=["reset link"], excludes=["reset link"]),
        answer="Use the reset link.",
    )

    assert result.matched_expected_fragments == ["reset link"]
    assert result.matched_excluded_fragments == ["reset link"]
    assert result.passed is False


@pytest.mark.parametrize("answer", ["", " \n\t "])
def test_empty_answer_is_an_outcome_with_stable_diagnostics(answer: str):
    result = evaluate_answer(case=case(contains=["reset link"]), answer=answer)

    assert result.answer == answer
    assert result.passed is False
    assert result.missing_expected_fragments == ["reset link"]
    assert result.citation_count == 0
    assert result.failure_reasons == ["empty_answer", "missing_expected_fragment"]


def test_no_expectations_is_unevaluable_not_passing():
    result = evaluate_answer(case=case(), answer="A fluent but unchecked answer.")

    assert result.passed is None
    assert result.failure_reasons == ["no_answer_expectations"]


def test_citation_requirement_depends_on_expected_sources_and_can_be_disabled():
    required = evaluate_answer(case=case(sources=["account-guide"]), answer="Answer")
    not_required = evaluate_answer(case=case(), answer="Answer")
    disabled = evaluate_answer(
        case=case(sources=["account-guide"]),
        answer="Answer",
        options=AnswerEvaluationOptions(require_citations_when_sources_expected=False),
    )

    assert required.passed is False
    assert required.failure_reasons == ["missing_required_citation"]
    assert not_required.passed is None
    assert disabled.passed is None


def test_citation_count_preserves_duplicates_while_source_diagnostics_are_unique_and_stable():
    result = evaluate_answer(
        case=case(sources=["doc-a", "doc-c"]),
        answer="Answer",
        citations=[citation("doc-b", "b-1"), citation("doc-a", "a-1"), citation("doc-b", "b-2")],
        retrieved_items=[item("doc-a", 1), item("doc-b", 2), item("doc-b", 3)],
    )

    assert result.citation_count == 3
    assert result.cited_source_ids == ["doc-b", "doc-a"]
    assert result.valid_citation_source_ids == ["doc-b", "doc-a"]
    assert result.invalid_citation_source_ids == []
    assert result.duplicate_citation_source_ids == ["doc-b"]
    assert result.cited_expected_source_ids == ["doc-a"]
    assert result.cited_unexpected_source_ids == ["doc-b"]
    assert result.uncited_expected_source_ids == ["doc-c"]
    assert result.failure_reasons == ["duplicate_citation"]
    assert result.passed is True


def test_citations_are_valid_only_when_every_document_was_in_retrieval():
    result = evaluate_answer(
        case=case(sources=["expected"]),
        answer="Answer",
        citations=[citation("expected"), citation("invented", "chunk-2")],
        retrieved_items=[item("expected", 1), item("other", 2)],
    )

    assert result.citations_valid is False
    assert result.valid_citation_source_ids == ["expected"]
    assert result.invalid_citation_source_ids == ["invented"]
    assert result.hallucination_detected is True
    assert result.passed is False
    assert result.failure_reasons == ["citation_not_in_retrieval"]


def test_retrieved_but_unexpected_citation_is_structurally_valid():
    result = evaluate_answer(
        case=case(sources=["expected"]),
        answer="Answer",
        citations=[citation("other")],
        retrieved_items=[item("other", 1)],
    )

    assert result.citations_valid is True
    assert result.hallucination_detected is False
    assert result.cited_unexpected_source_ids == ["other"]
    assert result.uncited_expected_source_ids == ["expected"]
    assert result.passed is True


def test_multiple_chunks_from_one_document_share_canonical_document_identity():
    result = evaluate_answer(
        case=case(sources=["guide"]),
        answer="Answer",
        citations=[citation("guide", "chunk-b")],
        retrieved_items=[item("guide", 1, "chunk-a"), item("guide", 2, "chunk-b")],
    )

    assert result.citations_valid is True
    assert result.cited_source_ids == ["guide"]


def test_citation_validation_is_none_without_citations_or_retrieval_context():
    no_citations = evaluate_answer(
        case=case(contains=["answer"]), answer="Answer", retrieved_items=[item("doc", 1)]
    )
    no_context = evaluate_answer(
        case=case(sources=["doc"]), answer="Answer", citations=[citation("doc")]
    )
    disabled = evaluate_answer(
        case=case(sources=["doc"]),
        answer="Answer",
        citations=[citation("invented")],
        retrieved_items=[],
        options=AnswerEvaluationOptions(validate_citations_against_retrieval=False),
    )

    assert no_citations.citations_valid is None
    assert no_citations.hallucination_detected is None
    assert no_context.citations_valid is None
    assert no_context.hallucination_detected is None
    assert no_context.passed is True
    assert no_context.failure_reasons == ["citation_validation_unavailable"]
    assert disabled.citations_valid is None
    assert disabled.hallucination_detected is None
    assert disabled.passed is True


def test_empty_retrieval_context_invalidates_a_present_citation():
    result = evaluate_answer(
        case=case(sources=["doc"]),
        answer="",
        citations=[citation("doc")],
        retrieved_items=[],
    )

    assert result.citation_count == 1
    assert result.citations_valid is False
    assert result.passed is False
    assert result.failure_reasons == ["empty_answer", "citation_not_in_retrieval"]


def test_multiple_failures_are_unique_and_in_stable_rule_order():
    result = evaluate_answer(
        case=case(contains=["reset link"], excludes=["send password"], sources=["expected"]),
        answer="Send password",
        citations=[citation("invented"), citation("invented", "chunk-2")],
        retrieved_items=[item("expected", 1)],
    )

    assert result.passed is False
    assert result.failure_reasons == [
        "missing_expected_fragment",
        "contains_excluded_fragment",
        "citation_not_in_retrieval",
        "duplicate_citation",
    ]


def test_inputs_are_not_mutated_and_repeated_evaluation_is_equivalent():
    evaluation_case = case(contains=["reset link"], sources=["guide"])
    citations = [citation("guide")]
    retrieved = [item("guide", 1)]
    answer = "  Use the RESET   LINK.  "
    before = deepcopy((evaluation_case, citations, retrieved))

    first = evaluate_answer(
        case=evaluation_case, answer=answer, citations=citations, retrieved_items=retrieved
    )
    second = evaluate_answer(
        case=evaluation_case, answer=answer, citations=citations, retrieved_items=retrieved
    )

    assert first == second
    assert (evaluation_case, citations, retrieved) == before
    assert first.answer == answer


def test_non_string_answer_is_rejected_as_programmer_misuse():
    with pytest.raises(ValueError, match="answer must be a string"):
        evaluate_answer(case=case(), answer=None)  # type: ignore[arg-type]


def test_chat_response_adapter_extracts_answer_and_document_citations_without_mutation():
    response = ChatResponse(
        message="Use the reset link.",
        sources=[
            SourceReference(id="guide", title="Account guide"),
            SourceReference(id="guide", title="Account guide"),
        ],
    )
    before = response.model_copy(deep=True)

    result = evaluate_chat_response(
        case=case(contains=["reset link"], sources=["guide"]),
        response=response,
        retrieved_items=[item("guide", 1)],
    )

    assert result.answer == "Use the reset link."
    assert result.citation_count == 2
    assert result.cited_source_ids == ["guide"]
    assert result.duplicate_citation_source_ids == ["guide"]
    assert result.citations_valid is True
    assert response == before


def test_chat_response_adapter_accepts_empty_source_list():
    result = evaluate_chat_response(
        case=case(contains=["answer"]),
        response=ChatResponse(message="Answer", sources=[]),
    )

    assert result.citation_count == 0
    assert result.passed is True


def evaluated_result(
    passed: bool | None, citation_count: int, citations_valid: bool | None
) -> AnswerEvaluationResult:
    return AnswerEvaluationResult(
        answer="Answer",
        passed=passed,
        citation_count=citation_count,
        citations_valid=citations_valid,
    )


def test_summary_aggregates_cases_and_includes_false_and_zero_values():
    results = [
        evaluated_result(True, 0, True),
        evaluated_result(False, 2, False),
        evaluated_result(None, 1, None),
    ]
    before = deepcopy(results)

    summary = summarise_answer_results(results)

    assert summary.evaluated_cases == 3
    assert summary.evaluable_cases == 2
    assert summary.passed_cases == 1
    assert summary.failed_cases == 1
    assert summary.unevaluable_cases == 1
    assert summary.pass_rate == pytest.approx(0.5)
    assert summary.average_citation_count == pytest.approx(1.0)
    assert summary.citation_validity_rate == pytest.approx(0.5)
    assert results == before


def test_summary_handles_empty_and_all_unevaluable_results():
    empty = summarise_answer_results([])
    unevaluable = summarise_answer_results([evaluated_result(None, 0, None)])

    assert empty.evaluated_cases == 0
    assert empty.evaluable_cases == 0
    assert empty.pass_rate is None
    assert empty.average_citation_count == 0.0
    assert empty.citation_validity_rate is None
    assert unevaluable.pass_rate is None
    assert unevaluable.average_citation_count == 0.0
