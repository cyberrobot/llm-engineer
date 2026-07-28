from unittest.mock import patch

from assistant.domain.evaluation import calculate_evaluation_metrics, evaluate_answer


def test_supported_answer_sentence_returns_supported_true():
    chunks = [{"id": "chunk-1", "text": "Staff must wear surgical scrubs.", "embedding": [1, 0]}]

    with patch("assistant.domain.citation_verifier.get_embedding", return_value=[1, 0]):
        assert evaluate_answer("Staff must wear surgical scrubs.", chunks) == [
            {
                "sentence": "Staff must wear surgical scrubs.",
                "supported": True,
                "source_ids": ["chunk-1"],
                "support_score": 1.0,
            }
        ]


def test_unsupported_answer_sentence_returns_supported_false():
    chunks = [{"id": "chunk-1", "text": "Staff must wear surgical scrubs.", "embedding": [0, 1]}]

    with patch("assistant.domain.citation_verifier.get_embedding", return_value=[1, 0]):
        assert evaluate_answer("Visitors must wear blue badges.", chunks) == [
            {
                "sentence": "Visitors must wear blue badges.",
                "supported": False,
                "source_ids": [],
                "support_score": 0.0,
            }
        ]


def test_multiple_sentences_preserve_order():
    chunks = [
        {"id": "chunk-1", "text": "Staff must wear surgical scrubs.", "embedding": [1, 0]},
        {"id": "chunk-2", "text": "Masks are required in operating rooms.", "embedding": [0, 1]},
    ]

    with patch("assistant.domain.citation_verifier.get_embedding", side_effect=[[1, 0], [0, 1]]):
        assert evaluate_answer(
            "Staff must wear surgical scrubs. Masks are required in operating rooms.",
            chunks,
        ) == [
            {
                "sentence": "Staff must wear surgical scrubs.",
                "supported": True,
                "source_ids": ["chunk-1"],
                "support_score": 1.0,
            },
            {
                "sentence": "Masks are required in operating rooms.",
                "supported": True,
                "source_ids": ["chunk-2"],
                "support_score": 1.0,
            },
        ]


def test_empty_answer_returns_empty_list():
    chunks = [{"id": "chunk-1", "text": "Staff must wear surgical scrubs."}]

    assert evaluate_answer("", chunks) == []
    assert evaluate_answer(" \n\t ", chunks) == []


def test_empty_chunks_returns_unsupported_sentence_results():
    assert evaluate_answer("Staff must wear surgical scrubs.", []) == [
        {
            "sentence": "Staff must wear surgical scrubs.",
            "supported": False,
            "source_ids": [],
            "support_score": 0.0,
        }
    ]


def test_calculate_evaluation_metrics_with_mixed_results():
    results = [
        {
            "sentence": "Staff must wear surgical scrubs.",
            "supported": True,
            "source_ids": ["chunk-1"],
        },
        {
            "sentence": "Jewellery is allowed.",
            "supported": False,
            "source_ids": [],
        },
    ]

    assert calculate_evaluation_metrics(results) == {
        "groundedness_score": 0.5,
        "verified_sentences": 1,
        "unsupported_claims": 1,
        "total_sentences": 2,
        "citation_count": 1,
    }


def test_calculate_evaluation_metrics_with_all_supported_results():
    results = [
        {
            "sentence": "Staff must wear surgical scrubs.",
            "supported": True,
            "source_ids": ["chunk-1"],
        },
        {
            "sentence": "Masks are required in operating rooms.",
            "supported": True,
            "source_ids": ["chunk-2"],
        },
    ]

    assert calculate_evaluation_metrics(results) == {
        "groundedness_score": 1.0,
        "verified_sentences": 2,
        "unsupported_claims": 0,
        "total_sentences": 2,
        "citation_count": 2,
    }


def test_calculate_evaluation_metrics_with_all_unsupported_results():
    results = [
        {
            "sentence": "Jewellery is allowed.",
            "supported": False,
            "source_ids": [],
        },
        {
            "sentence": "Visitors must wear blue badges.",
            "supported": False,
            "source_ids": [],
        },
    ]

    assert calculate_evaluation_metrics(results) == {
        "groundedness_score": 0.0,
        "verified_sentences": 0,
        "unsupported_claims": 2,
        "total_sentences": 2,
        "citation_count": 0,
    }


def test_calculate_evaluation_metrics_with_empty_results():
    assert calculate_evaluation_metrics([]) == {
        "groundedness_score": 0,
        "verified_sentences": 0,
        "unsupported_claims": 0,
        "total_sentences": 0,
        "citation_count": 0,
    }


def test_calculate_evaluation_metrics_counts_duplicate_source_ids_once():
    results = [
        {
            "sentence": "Staff must wear surgical scrubs.",
            "supported": True,
            "source_ids": ["chunk-1", "chunk-1"],
        },
        {
            "sentence": "Masks are required in operating rooms.",
            "supported": True,
            "source_ids": ["chunk-1", "chunk-2"],
        },
        {
            "sentence": "Jewellery is allowed.",
            "supported": False,
            "source_ids": ["chunk-3"],
        },
    ]

    assert calculate_evaluation_metrics(results) == {
        "groundedness_score": 0.67,
        "verified_sentences": 2,
        "unsupported_claims": 1,
        "total_sentences": 3,
        "citation_count": 2,
    }
