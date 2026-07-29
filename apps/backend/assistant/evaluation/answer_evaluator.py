"""Pure, deterministic rule-based evaluation of already-generated answers."""

from collections.abc import Sequence

from assistant.domain import Citation
from assistant.evaluation.models import (
    AnswerEvaluationOptions,
    AnswerEvaluationResult,
    AnswerEvaluationSummary,
    EvaluationCase,
    RetrievedItem,
)

EMPTY_ANSWER = "empty_answer"
MISSING_EXPECTED_FRAGMENT = "missing_expected_fragment"
CONTAINS_EXCLUDED_FRAGMENT = "contains_excluded_fragment"
MISSING_REQUIRED_CITATION = "missing_required_citation"
CITATION_NOT_IN_RETRIEVAL = "citation_not_in_retrieval"
DUPLICATE_CITATION = "duplicate_citation"
NO_ANSWER_EXPECTATIONS = "no_answer_expectations"
CITATION_VALIDATION_UNAVAILABLE = "citation_validation_unavailable"


class AnswerEvaluationError(ValueError):
    """Raised when answer evaluation inputs violate the evaluator contract."""


def evaluate_answer(
    *,
    case: EvaluationCase,
    answer: str,
    citations: Sequence[Citation] | None = None,
    retrieved_items: Sequence[RetrievedItem] | None = None,
    options: AnswerEvaluationOptions | None = None,
) -> AnswerEvaluationResult:
    """Evaluate an answer using configured text and citation rules only."""

    if not isinstance(answer, str):
        raise AnswerEvaluationError("answer must be a string")

    configured = options or AnswerEvaluationOptions()
    citation_values = list(citations or ())
    citation_source_ids = [_citation_source_id(value) for value in citation_values]
    cited_source_ids, duplicate_source_ids = _unique_values(citation_source_ids)

    normalised_answer = _normalise_text(answer, configured)
    matched_expected, missing_expected = _partition_fragments(
        case.expected_answer_contains, normalised_answer, configured
    )
    matched_excluded, _ = _partition_fragments(
        case.expected_answer_excludes, normalised_answer, configured
    )

    expected_set = set(case.expected_source_ids)
    cited_expected = [value for value in cited_source_ids if value in expected_set]
    cited_unexpected = [value for value in cited_source_ids if value not in expected_set]
    cited_set = set(cited_source_ids)
    uncited_expected = [value for value in case.expected_source_ids if value not in cited_set]

    citations_valid: bool | None = None
    valid_citations: list[str] = []
    invalid_citations: list[str] = []
    validation_applicable = bool(citation_values) and (
        configured.validate_citations_against_retrieval and retrieved_items is not None
    )
    if (
        citation_values
        and configured.validate_citations_against_retrieval
        and retrieved_items is not None
    ):
        retrieved_source_ids = {
            item.document_id for item in retrieved_items if item.document_id is not None
        }
        valid_citations = [value for value in cited_source_ids if value in retrieved_source_ids]
        invalid_citations = [
            value for value in cited_source_ids if value not in retrieved_source_ids
        ]
        citations_valid = not invalid_citations

    required_applicable = bool(case.expected_answer_contains)
    if configured.require_all_expected_fragments:
        required_passed = not missing_expected
    else:
        required_passed = bool(matched_expected)

    exclusion_applicable = bool(case.expected_answer_excludes)
    exclusion_passed = not matched_excluded
    citation_requirement_applicable = bool(case.expected_source_ids) and (
        configured.require_citations_when_sources_expected
    )
    citation_requirement_passed = bool(citation_values)

    applicable_checks: list[bool] = []
    if required_applicable:
        applicable_checks.append(required_passed)
    if exclusion_applicable:
        applicable_checks.append(exclusion_passed)
    if citation_requirement_applicable:
        applicable_checks.append(citation_requirement_passed)
    if validation_applicable:
        applicable_checks.append(citations_valid is True)
    passed = all(applicable_checks) if applicable_checks else None

    reasons: list[str] = []
    if not answer.strip():
        reasons.append(EMPTY_ANSWER)
    if required_applicable and not required_passed:
        reasons.append(MISSING_EXPECTED_FRAGMENT)
    if exclusion_applicable and not exclusion_passed:
        reasons.append(CONTAINS_EXCLUDED_FRAGMENT)
    if citation_requirement_applicable and not citation_requirement_passed:
        reasons.append(MISSING_REQUIRED_CITATION)
    if citations_valid is False:
        reasons.append(CITATION_NOT_IN_RETRIEVAL)
    if duplicate_source_ids:
        reasons.append(DUPLICATE_CITATION)
    if passed is None:
        reasons.append(NO_ANSWER_EXPECTATIONS)
    if (
        citation_values
        and configured.validate_citations_against_retrieval
        and retrieved_items is None
    ):
        reasons.append(CITATION_VALIDATION_UNAVAILABLE)

    return AnswerEvaluationResult(
        answer=answer,
        passed=passed,
        matched_expected_fragments=matched_expected,
        missing_expected_fragments=missing_expected,
        matched_excluded_fragments=matched_excluded,
        citation_count=len(citation_values),
        citations_valid=citations_valid,
        hallucination_detected=None if citations_valid is None else not citations_valid,
        cited_source_ids=cited_source_ids,
        valid_citation_source_ids=valid_citations,
        invalid_citation_source_ids=invalid_citations,
        duplicate_citation_source_ids=duplicate_source_ids,
        cited_expected_source_ids=cited_expected,
        cited_unexpected_source_ids=cited_unexpected,
        uncited_expected_source_ids=uncited_expected,
        failure_reasons=reasons,
        metadata={
            "checks_evaluated": {
                "required_fragments": required_applicable,
                "prohibited_fragments": exclusion_applicable,
                "citation_requirement": citation_requirement_applicable,
                "citation_validation": validation_applicable,
            },
            "canonical_source_identity": "document_id",
            "case_sensitive": configured.case_sensitive,
            "normalise_whitespace": configured.normalise_whitespace,
            "require_all_expected_fragments": configured.require_all_expected_fragments,
        },
    )


def summarise_answer_results(
    results: Sequence[AnswerEvaluationResult],
) -> AnswerEvaluationSummary:
    """Aggregate answer results without treating unevaluable values as failures."""

    evaluable = [result for result in results if result.passed is not None]
    passed_count = sum(result.passed is True for result in evaluable)
    failed_count = sum(result.passed is False for result in evaluable)
    citation_validity = [
        result.citations_valid for result in results if result.citations_valid is not None
    ]

    return AnswerEvaluationSummary(
        evaluated_cases=len(results),
        evaluable_cases=len(evaluable),
        passed_cases=passed_count,
        failed_cases=failed_count,
        unevaluable_cases=len(results) - len(evaluable),
        pass_rate=passed_count / len(evaluable) if evaluable else None,
        average_citation_count=(
            sum(result.citation_count or 0 for result in results) / len(results) if results else 0.0
        ),
        citation_validity_rate=(
            sum(value is True for value in citation_validity) / len(citation_validity)
            if citation_validity
            else None
        ),
    )


def _normalise_text(value: str, options: AnswerEvaluationOptions) -> str:
    normalised = " ".join(value.split()) if options.normalise_whitespace else value.strip()
    return normalised if options.case_sensitive else normalised.casefold()


def _partition_fragments(
    fragments: Sequence[str], answer: str, options: AnswerEvaluationOptions
) -> tuple[list[str], list[str]]:
    matched: list[str] = []
    unmatched: list[str] = []
    for fragment in fragments:
        target = _normalise_text(fragment, options)
        (matched if target in answer else unmatched).append(fragment)
    return matched, unmatched


def _citation_source_id(citation: Citation) -> str:
    try:
        source_id = citation.document_id
    except AttributeError as exc:
        raise AnswerEvaluationError("citations must provide document_id") from exc
    if not isinstance(source_id, str) or not source_id.strip():
        raise AnswerEvaluationError("citation document_id must be a non-empty string")
    return source_id


def _unique_values(values: Sequence[str]) -> tuple[list[str], list[str]]:
    unique: list[str] = []
    duplicates: list[str] = []
    seen: set[str] = set()
    duplicate_seen: set[str] = set()
    for value in values:
        if value not in seen:
            unique.append(value)
            seen.add(value)
        elif value not in duplicate_seen:
            duplicates.append(value)
            duplicate_seen.add(value)
    return unique, duplicates
