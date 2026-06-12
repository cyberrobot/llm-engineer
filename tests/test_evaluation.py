from api.services.evaluation import evaluate_answer


def test_supported_answer_sentence_returns_supported_true():
    chunks = [{"id": "chunk-1", "text": "Staff must wear surgical scrubs."}]

    assert evaluate_answer("Staff must wear surgical scrubs.", chunks) == [
        {
            "sentence": "Staff must wear surgical scrubs.",
            "supported": True,
            "source_ids": ["chunk-1"],
        }
    ]


def test_unsupported_answer_sentence_returns_supported_false():
    chunks = [{"id": "chunk-1", "text": "Staff must wear surgical scrubs."}]

    assert evaluate_answer("Visitors must wear blue badges.", chunks) == [
        {
            "sentence": "Visitors must wear blue badges.",
            "supported": False,
            "source_ids": [],
        }
    ]


def test_multiple_sentences_preserve_order():
    chunks = [
        {"id": "chunk-1", "text": "Staff must wear surgical scrubs."},
        {"id": "chunk-2", "text": "Masks are required in operating rooms."},
    ]

    assert evaluate_answer(
        "Staff must wear surgical scrubs. Masks are required in operating rooms.",
        chunks,
    ) == [
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
        }
    ]
