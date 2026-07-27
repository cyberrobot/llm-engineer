from unittest.mock import patch

from api.services.citation_verifier import verify_sentence


def test_supported_sentence_returns_best_source_id_and_score():
    chunks = [{"id": "chunk-1", "text": "Staff must wear surgical scrubs.", "embedding": [1, 0]}]

    with patch("api.services.citation_verifier.get_embedding", return_value=[1, 0]) as get_embedding:
        result = verify_sentence("Staff must wear surgical scrubs.", chunks)

    assert result == {
        "sentence": "Staff must wear surgical scrubs.",
        "supported": True,
        "source_ids": ["chunk-1"],
        "support_score": 1.0,
    }
    get_embedding.assert_called_once_with("Staff must wear surgical scrubs.")


def test_unsupported_sentence_returns_score_without_source_ids():
    chunks = [{"id": "chunk-1", "text": "Staff must wear surgical scrubs.", "embedding": [0, 1]}]

    with patch("api.services.citation_verifier.get_embedding", return_value=[1, 0]):
        result = verify_sentence("Visitors must wear blue badges.", chunks)

    assert result == {
        "sentence": "Visitors must wear blue badges.",
        "supported": False,
        "source_ids": [],
        "support_score": 0.0,
    }


def test_all_matching_chunks_are_returned():
    chunks = [
        {"id": "chunk-1", "text": "Related policy.", "embedding": [0.8, 0.6]},
        {"id": "chunk-2", "text": "Exact policy.", "embedding": [1, 0]},
        {"id": "chunk-3", "text": "Unrelated policy.", "embedding": [0, 1]},
    ]

    with patch("api.services.citation_verifier.get_embedding", return_value=[1, 0]):
        result = verify_sentence("Staff must wear surgical scrubs.", chunks)

    assert result == {
        "sentence": "Staff must wear surgical scrubs.",
        "supported": True,
        "source_ids": ["chunk-1", "chunk-2"],
        "support_score": 1.0,
    }


def test_empty_sentence_returns_unsupported_without_embedding():
    chunks = [{"id": "chunk-1", "text": "Staff must wear surgical scrubs.", "embedding": [1, 0]}]

    with patch("api.services.citation_verifier.get_embedding") as get_embedding:
        assert verify_sentence("", chunks) == {
            "sentence": "",
            "supported": False,
            "source_ids": [],
            "support_score": 0.0,
        }
        assert verify_sentence(" \n\t ", chunks) == {
            "sentence": " \n\t ",
            "supported": False,
            "source_ids": [],
            "support_score": 0.0,
        }

    get_embedding.assert_not_called()


def test_empty_chunks_list_returns_unsupported():
    with patch("api.services.citation_verifier.get_embedding") as get_embedding:
        result = verify_sentence("Staff must wear surgical scrubs.", [])

    assert result == {
        "sentence": "Staff must wear surgical scrubs.",
        "supported": False,
        "source_ids": [],
        "support_score": 0.0,
    }
    get_embedding.assert_not_called()


def test_fallback_embedding_is_used_when_chunk_embedding_is_missing():
    chunks = [{"id": "chunk-1", "text": "Staff must wear surgical scrubs."}]

    with patch(
        "api.services.citation_verifier.get_embedding",
        side_effect=[[1, 0], [1, 0]],
    ) as get_embedding:
        result = verify_sentence("Staff must wear surgical scrubs.", chunks)

    assert result == {
        "sentence": "Staff must wear surgical scrubs.",
        "supported": True,
        "source_ids": ["chunk-1"],
        "support_score": 1.0,
    }
    assert get_embedding.call_args_list[0].args == ("Staff must wear surgical scrubs.",)
    assert get_embedding.call_args_list[1].args == ("Staff must wear surgical scrubs.",)


def test_chunks_missing_id_or_embedding_source_are_skipped():
    chunks = [
        {"id": "chunk-1"},
        {"text": "Staff must wear surgical scrubs.", "embedding": [1, 0]},
        {"id": "", "text": "Staff must wear surgical scrubs.", "embedding": [1, 0]},
        {"id": "chunk-2", "text": ""},
        {"id": "chunk-3", "text": "Staff must wear surgical scrubs.", "embedding": [1, 0]},
    ]

    with patch("api.services.citation_verifier.get_embedding", return_value=[1, 0]):
        result = verify_sentence("Staff must wear surgical scrubs.", chunks)

    assert result == {
        "sentence": "Staff must wear surgical scrubs.",
        "supported": True,
        "source_ids": ["chunk-3"],
        "support_score": 1.0,
    }
