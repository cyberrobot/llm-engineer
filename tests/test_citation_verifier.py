from api.services.citation_verifier import verify_sentence


def test_exact_matching_sentence_returns_supported():
    chunks = [{"id": "chunk-1", "text": "The capital of France is Paris."}]

    assert verify_sentence("The capital of France is Paris.", chunks) == (
        True,
        ["chunk-1"],
    )


def test_unrelated_sentence_returns_unsupported():
    chunks = [{"id": "chunk-1", "text": "The capital of France is Paris."}]

    assert verify_sentence("Jupiter is the largest planet.", chunks) == (False, [])


def test_empty_sentence_returns_unsupported():
    chunks = [{"id": "chunk-1", "text": "The capital of France is Paris."}]

    assert verify_sentence("", chunks) == (False, [])
    assert verify_sentence(" \n\t ", chunks) == (False, [])


def test_empty_chunks_list_returns_unsupported():
    assert verify_sentence("The capital of France is Paris.", []) == (False, [])


def test_chunks_missing_id_or_text_are_skipped():
    chunks = [
        {"id": "chunk-1"},
        {"text": "The capital of France is Paris."},
        {"id": "", "text": "The capital of France is Paris."},
        {"id": "chunk-2", "text": ""},
        {"id": "chunk-3", "text": "The capital of France is Paris."},
    ]

    assert verify_sentence("The capital of France is Paris.", chunks) == (
        True,
        ["chunk-3"],
    )


def test_multiple_matching_chunks_return_multiple_source_ids():
    chunks = [
        {"id": "chunk-1", "text": "The capital of France is Paris."},
        {"id": "chunk-2", "text": "The capital of France is Paris."},
        {"id": "chunk-3", "text": "Saturn has rings."},
    ]

    assert verify_sentence("The capital of France is Paris.", chunks) == (
        True,
        ["chunk-1", "chunk-2"],
    )
