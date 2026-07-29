"""Pure, deterministic retrieval-quality evaluation."""

from collections.abc import Sequence

from assistant.evaluation.models import (
    EvaluationCase,
    RetrievalEvaluationResult,
    RetrievalEvaluationSummary,
    RetrievedItem,
)

NO_RETRIEVAL_RESULTS = "no_retrieval_results"
NO_EXPECTED_SOURCES = "no_expected_sources"
NO_EXPECTED_SOURCE_RETRIEVED = "no_expected_source_retrieved"
PARTIAL_EXPECTED_SOURCE_RECALL = "partial_expected_source_recall"


class RetrievalEvaluationError(ValueError):
    """Raised when retrieval evaluation inputs violate the evaluator contract."""


def evaluate_retrieval(
    *,
    case: EvaluationCase,
    retrieved_items: Sequence[RetrievedItem],
    k: int | None = None,
) -> RetrievalEvaluationResult:
    """Evaluate document-level retrieval quality for one already-retrieved case."""

    _validate_k(k)
    ranked_items = _normalise_ranked_items(retrieved_items)
    considered_items = ranked_items[:k] if k is not None else ranked_items
    expected_source_ids = list(case.expected_source_ids)

    if not expected_source_ids:
        retrieved_source_ids = [
            item.document_id for item in considered_items if item.document_id is not None
        ]
        unique_retrieved, duplicates = _unique_sources(retrieved_source_ids)
        return RetrievalEvaluationResult(
            retrieved_items=[item.model_copy(deep=True) for item in considered_items],
            precision_at_k=None,
            recall_at_k=None,
            reciprocal_rank=None,
            hit=None,
            expected_source_ids=[],
            matched_source_ids=[],
            unmatched_expected_source_ids=[],
            unexpected_retrieved_source_ids=unique_retrieved,
            duplicate_retrieved_source_ids=duplicates,
            evaluated_at_k=k,
            failure_reasons=[NO_EXPECTED_SOURCES],
        )

    missing_identity_ranks = [item.rank for item in considered_items if item.document_id is None]
    if missing_identity_ranks:
        rendered_ranks = ", ".join(str(rank) for rank in missing_identity_ranks)
        raise RetrievalEvaluationError(
            "Retrieved items require document_id for document-level source matching; "
            f"missing at ranks: {rendered_ranks}"
        )

    retrieved_source_ids = [
        item.document_id for item in considered_items if item.document_id is not None
    ]
    unique_retrieved, duplicates = _unique_sources(retrieved_source_ids)
    expected_set = set(expected_source_ids)
    matched = [source_id for source_id in unique_retrieved if source_id in expected_set]
    matched_set = set(matched)
    unmatched = [source_id for source_id in expected_source_ids if source_id not in matched_set]
    unexpected = [source_id for source_id in unique_retrieved if source_id not in expected_set]

    precision = len(matched) / len(unique_retrieved) if unique_retrieved else 0.0
    recall = len(matched) / len(expected_source_ids)
    hit = bool(matched)
    reciprocal_rank = _reciprocal_rank(retrieved_source_ids, expected_set)

    failure_reasons: list[str] = []
    if not considered_items:
        failure_reasons.append(NO_RETRIEVAL_RESULTS)
    if not matched:
        failure_reasons.append(NO_EXPECTED_SOURCE_RETRIEVED)
    elif unmatched:
        failure_reasons.append(PARTIAL_EXPECTED_SOURCE_RECALL)

    return RetrievalEvaluationResult(
        retrieved_items=[item.model_copy(deep=True) for item in considered_items],
        precision_at_k=precision,
        recall_at_k=recall,
        reciprocal_rank=reciprocal_rank,
        hit=hit,
        expected_source_ids=expected_source_ids,
        matched_source_ids=matched,
        unmatched_expected_source_ids=unmatched,
        unexpected_retrieved_source_ids=unexpected,
        duplicate_retrieved_source_ids=duplicates,
        evaluated_at_k=k,
        failure_reasons=failure_reasons,
    )


def summarise_retrieval_results(
    results: Sequence[RetrievalEvaluationResult],
) -> RetrievalEvaluationSummary:
    """Average available per-case metrics without treating missing values as zero."""

    precision_values = [
        result.precision_at_k for result in results if result.precision_at_k is not None
    ]
    recall_values = [result.recall_at_k for result in results if result.recall_at_k is not None]
    hit_values = [result.hit for result in results if result.hit is not None]
    reciprocal_rank_values = [
        result.reciprocal_rank for result in results if result.reciprocal_rank is not None
    ]

    return RetrievalEvaluationSummary(
        evaluated_cases=len(results),
        source_evaluable_cases=len(hit_values),
        precision_at_k=_mean(precision_values),
        recall_at_k=_mean(recall_values),
        hit_rate=_mean([float(hit) for hit in hit_values]),
        mean_reciprocal_rank=_mean(reciprocal_rank_values),
        average_retrieved_items=(
            sum(len(result.retrieved_items) for result in results) / len(results)
            if results
            else 0.0
        ),
    )


def _validate_k(k: int | None) -> None:
    if k is not None and (isinstance(k, bool) or not isinstance(k, int) or k < 1):
        raise RetrievalEvaluationError("k must be a positive integer")


def _normalise_ranked_items(items: Sequence[RetrievedItem]) -> list[RetrievedItem]:
    copied = [item.model_copy(deep=True) for item in items]
    ranks = [item.rank for item in copied]
    if len(ranks) != len(set(ranks)):
        raise RetrievalEvaluationError("Retrieved items must not contain duplicate ranks")

    ranked = sorted(copied, key=lambda item: item.rank)
    sorted_ranks = [item.rank for item in ranked]
    if sorted_ranks != list(range(1, len(ranked) + 1)):
        raise RetrievalEvaluationError(
            "Retrieved item ranks must form an ascending sequence from 1"
        )
    return ranked


def _unique_sources(source_ids: Sequence[str]) -> tuple[list[str], list[str]]:
    unique: list[str] = []
    duplicates: list[str] = []
    seen: set[str] = set()
    duplicate_seen: set[str] = set()
    for source_id in source_ids:
        if source_id not in seen:
            unique.append(source_id)
            seen.add(source_id)
        elif source_id not in duplicate_seen:
            duplicates.append(source_id)
            duplicate_seen.add(source_id)
    return unique, duplicates


def _reciprocal_rank(source_ids: Sequence[str], expected_source_ids: set[str]) -> float:
    for rank, source_id in enumerate(source_ids, start=1):
        if source_id in expected_source_ids:
            return 1 / rank
    return 0.0


def _mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None
