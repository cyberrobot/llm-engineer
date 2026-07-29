from copy import deepcopy

import pytest

from assistant.domain import KnowledgeChunk, KnowledgeDocument
from assistant.evaluation import (
    EvaluationCase,
    RetrievalEvaluationError,
    RetrievalEvaluationResult,
    RetrievedItem,
    evaluate_retrieval,
    summarise_retrieval_results,
    to_evaluation_retrieved_items,
)


def evaluation_case(*expected_source_ids: str) -> EvaluationCase:
    return EvaluationCase(
        id="reset-password",
        question="How do I reset my password?",
        expected_source_ids=list(expected_source_ids),
    )


def item(source_id: str | None, rank: int, *, item_id: str | None = None) -> RetrievedItem:
    return RetrievedItem(
        id=item_id or f"chunk-{rank}",
        chunk_id=item_id or f"chunk-{rank}",
        document_id=source_id,
        rank=rank,
    )


@pytest.mark.parametrize(
    ("retrieved", "expected_precision", "expected_recall"),
    [
        ([item("account", 1), item("security", 2)], 1.0, 1.0),
        ([item("account", 1), item("other", 2)], 0.5, 0.5),
        ([item("other", 1), item("unrelated", 2)], 0.0, 0.0),
        ([], 0.0, 0.0),
    ],
)
def test_evaluate_retrieval_calculates_precision_and_recall(
    retrieved: list[RetrievedItem], expected_precision: float, expected_recall: float
):
    result = evaluate_retrieval(
        case=evaluation_case("account", "security"), retrieved_items=retrieved
    )

    assert result.precision_at_k == pytest.approx(expected_precision)
    assert result.recall_at_k == pytest.approx(expected_recall)


def test_evaluate_retrieval_applies_k_without_mutating_or_reordering_inputs():
    retrieved = [item("security", 3), item("other", 2), item("account", 1)]
    original = deepcopy(retrieved)

    result = evaluate_retrieval(
        case=evaluation_case("account", "security"), retrieved_items=retrieved, k=2
    )

    assert [retrieved_item.document_id for retrieved_item in result.retrieved_items] == [
        "account",
        "other",
    ]
    assert result.evaluated_at_k == 2
    assert result.precision_at_k == pytest.approx(0.5)
    assert result.recall_at_k == pytest.approx(0.5)
    assert retrieved == original


def test_evaluate_retrieval_uses_every_item_when_k_exceeds_result_count():
    result = evaluate_retrieval(
        case=evaluation_case("security"),
        retrieved_items=[item("other", 1), item("security", 2)],
        k=10,
    )

    assert len(result.retrieved_items) == 2
    assert result.hit is True
    assert result.reciprocal_rank == pytest.approx(0.5)


def test_k_excluding_all_relevant_sources_produces_zero_quality_metrics():
    result = evaluate_retrieval(
        case=evaluation_case("expected"),
        retrieved_items=[item("other", 1), item("expected", 2)],
        k=1,
    )

    assert result.precision_at_k == 0.0
    assert result.recall_at_k == 0.0
    assert result.hit is False
    assert result.reciprocal_rank == 0.0


@pytest.mark.parametrize(
    ("source_ids", "k", "expected_hit", "expected_rank"),
    [
        (["expected", "other"], None, True, 1.0),
        (["other", "expected"], None, True, 0.5),
        (["other", "another"], None, False, 0.0),
        (["other", "expected"], 1, False, 0.0),
        (["other", "another", "expected"], None, True, 1 / 3),
    ],
)
def test_evaluate_retrieval_calculates_hit_and_reciprocal_rank(
    source_ids: list[str], k: int | None, expected_hit: bool, expected_rank: float
):
    retrieved = [item(source_id, rank) for rank, source_id in enumerate(source_ids, start=1)]

    result = evaluate_retrieval(case=evaluation_case("expected"), retrieved_items=retrieved, k=k)

    assert result.hit is expected_hit
    assert result.reciprocal_rank == pytest.approx(expected_rank)


def test_duplicate_documents_are_deduplicated_for_source_metrics_but_not_raw_rank():
    retrieved = [
        item("irrelevant", 1, item_id="irrelevant-1"),
        item("irrelevant", 2, item_id="irrelevant-2"),
        item("expected", 3, item_id="expected-1"),
        item("expected", 4, item_id="expected-2"),
    ]

    result = evaluate_retrieval(case=evaluation_case("expected"), retrieved_items=retrieved)

    assert result.precision_at_k == pytest.approx(0.5)
    assert result.recall_at_k == pytest.approx(1.0)
    assert result.reciprocal_rank == pytest.approx(1 / 3)
    assert result.matched_source_ids == ["expected"]
    assert result.unexpected_retrieved_source_ids == ["irrelevant"]
    assert result.duplicate_retrieved_source_ids == ["irrelevant", "expected"]
    assert len(result.retrieved_items) == 4


def test_diagnostics_preserve_case_and_retrieval_order():
    result = evaluate_retrieval(
        case=evaluation_case("expected-b", "missing", "expected-a"),
        retrieved_items=[
            item("unexpected-b", 1),
            item("expected-a", 2),
            item("unexpected-a", 3),
            item("expected-b", 4),
        ],
    )

    assert result.matched_source_ids == ["expected-a", "expected-b"]
    assert result.unmatched_expected_source_ids == ["missing"]
    assert result.unexpected_retrieved_source_ids == ["unexpected-b", "unexpected-a"]
    assert result.failure_reasons == ["partial_expected_source_recall"]


def test_complete_match_has_no_failure_reason():
    result = evaluate_retrieval(
        case=evaluation_case("expected"), retrieved_items=[item("expected", 1)]
    )

    assert result.failure_reasons == []
    assert result.unmatched_expected_source_ids == []
    assert result.unexpected_retrieved_source_ids == []


def test_empty_retrieval_is_a_valid_miss_with_deterministic_reasons():
    result = evaluate_retrieval(case=evaluation_case("expected"), retrieved_items=[])

    assert result.precision_at_k == 0.0
    assert result.recall_at_k == 0.0
    assert result.hit is False
    assert result.reciprocal_rank == 0.0
    assert result.unmatched_expected_source_ids == ["expected"]
    assert result.failure_reasons == [
        "no_retrieval_results",
        "no_expected_source_retrieved",
    ]


def test_no_matching_sources_has_a_specific_failure_reason():
    result = evaluate_retrieval(
        case=evaluation_case("expected"), retrieved_items=[item("other", 1)]
    )

    assert result.failure_reasons == ["no_expected_source_retrieved"]


def test_case_without_expected_sources_is_unevaluable_but_preserves_results():
    result = evaluate_retrieval(
        case=evaluation_case(),
        retrieved_items=[item("source-b", 2), item("source-a", 1)],
    )

    assert result.precision_at_k is None
    assert result.recall_at_k is None
    assert result.hit is None
    assert result.reciprocal_rank is None
    assert [retrieved.document_id for retrieved in result.retrieved_items] == [
        "source-a",
        "source-b",
    ]
    assert result.failure_reasons == ["no_expected_sources"]


def test_case_without_expected_sources_does_not_require_document_identity():
    result = evaluate_retrieval(case=evaluation_case(), retrieved_items=[item(None, 1)])

    assert result.precision_at_k is None
    assert result.retrieved_items[0].document_id is None
    assert result.failure_reasons == ["no_expected_sources"]


@pytest.mark.parametrize("k", [0, -1, True, 1.5])
def test_invalid_k_is_rejected(k: object):
    with pytest.raises(RetrievalEvaluationError, match="k must be a positive integer"):
        evaluate_retrieval(
            case=evaluation_case("expected"),
            retrieved_items=[],
            k=k,  # type: ignore[arg-type]
        )


def test_duplicate_ranks_are_rejected_without_mutating_inputs():
    retrieved = [item("expected", 1), item("other", 1)]
    original = deepcopy(retrieved)

    with pytest.raises(RetrievalEvaluationError, match="duplicate ranks"):
        evaluate_retrieval(case=evaluation_case("expected"), retrieved_items=retrieved)

    assert retrieved == original


def test_non_sequential_ranks_are_rejected_clearly():
    with pytest.raises(RetrievalEvaluationError, match="ascending sequence from 1"):
        evaluate_retrieval(
            case=evaluation_case("expected"),
            retrieved_items=[item("expected", 1), item("other", 3)],
        )


def test_missing_document_identity_is_rejected_when_source_matching_is_required():
    with pytest.raises(RetrievalEvaluationError, match="document_id"):
        evaluate_retrieval(case=evaluation_case("expected"), retrieved_items=[item(None, 1)])


def test_repeated_evaluation_is_equivalent_and_does_not_mutate_models():
    case = evaluation_case("expected")
    retrieved = [item("expected", 1)]
    case_before = case.model_copy(deep=True)
    retrieved_before = deepcopy(retrieved)

    first = evaluate_retrieval(case=case, retrieved_items=retrieved)
    second = evaluate_retrieval(case=case, retrieved_items=retrieved)

    assert first == second
    assert case == case_before
    assert retrieved == retrieved_before
    assert first.retrieved_items[0] is not retrieved[0]


def result(
    *,
    precision: float | None,
    recall: float | None,
    hit: bool | None,
    reciprocal_rank: float | None,
    count: int,
) -> RetrievalEvaluationResult:
    return RetrievalEvaluationResult(
        retrieved_items=[item(f"source-{rank}", rank) for rank in range(1, count + 1)],
        precision_at_k=precision,
        recall_at_k=recall,
        hit=hit,
        reciprocal_rank=reciprocal_rank,
    )


def test_summary_averages_quality_metrics_and_raw_retrieved_counts():
    results = [
        result(precision=1.0, recall=0.5, hit=True, reciprocal_rank=1.0, count=3),
        result(precision=0.0, recall=0.0, hit=False, reciprocal_rank=0.0, count=1),
        result(precision=None, recall=None, hit=None, reciprocal_rank=None, count=2),
    ]
    before = deepcopy(results)

    summary = summarise_retrieval_results(results)

    assert summary.evaluated_cases == 3
    assert summary.source_evaluable_cases == 2
    assert summary.precision_at_k == pytest.approx(0.5)
    assert summary.recall_at_k == pytest.approx(0.25)
    assert summary.hit_rate == pytest.approx(0.5)
    assert summary.mean_reciprocal_rank == pytest.approx(0.5)
    assert summary.average_retrieved_items == pytest.approx(2.0)
    assert results == before


def test_summary_returns_none_quality_metrics_when_all_cases_are_unevaluable():
    summary = summarise_retrieval_results(
        [result(precision=None, recall=None, hit=None, reciprocal_rank=None, count=1)]
    )

    assert summary.evaluated_cases == 1
    assert summary.source_evaluable_cases == 0
    assert summary.precision_at_k is None
    assert summary.recall_at_k is None
    assert summary.hit_rate is None
    assert summary.mean_reciprocal_rank is None
    assert summary.average_retrieved_items == 1.0


def test_summary_of_no_results_has_defined_count_average_only():
    summary = summarise_retrieval_results([])

    assert summary.evaluated_cases == 0
    assert summary.source_evaluable_cases == 0
    assert summary.precision_at_k is None
    assert summary.recall_at_k is None
    assert summary.hit_rate is None
    assert summary.mean_reciprocal_rank is None
    assert summary.average_retrieved_items == 0.0


def test_knowledge_chunk_adapter_preserves_contract_and_assigns_ranks():
    chunks = [
        KnowledgeChunk(
            id="chunk-b",
            document=KnowledgeDocument(
                id="document-b", title="Guide B", source_uri="https://example.com/b"
            ),
            content="Second result",
            score=0.75,
        ),
        KnowledgeChunk(
            id="chunk-a",
            document=KnowledgeDocument(id="document-a", title="Guide A"),
            content="First result",
            score=0.5,
        ),
    ]

    adapted = to_evaluation_retrieved_items(chunks)

    assert [value.rank for value in adapted] == [1, 2]
    assert [value.id for value in adapted] == ["chunk-b", "chunk-a"]
    assert [value.chunk_id for value in adapted] == ["chunk-b", "chunk-a"]
    assert [value.document_id for value in adapted] == ["document-b", "document-a"]
    assert [value.score for value in adapted] == [0.75, 0.5]
    assert [value.distance for value in adapted] == [None, None]
    assert [value.content for value in adapted] == ["Second result", "First result"]
    assert adapted[0].metadata == {
        "document_title": "Guide B",
        "source_uri": "https://example.com/b",
    }
    assert adapted[1].metadata == {"document_title": "Guide A"}


def test_knowledge_chunk_adapter_accepts_empty_input():
    assert to_evaluation_retrieved_items([]) == []
