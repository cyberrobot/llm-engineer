from datetime import datetime, timezone

from assistant.domain.clean_document import CleanDocument
from assistant.infrastructure.ingestion.semantic_text_chunker import SemanticTextChunker

RETRIEVED_AT = datetime(2026, 7, 29, 9, 0, tzinfo=timezone.utc)


def clean_document(text: str) -> CleanDocument:
    return CleanDocument(
        source_url="https://example.com/services",
        title="Services",
        text=text,
        content_hash="document-hash",
        retrieved_at=RETRIEVED_AT,
    )


def test_document_smaller_than_limit_produces_one_complete_chunk():
    chunks = SemanticTextChunker(chunk_size=200, overlap=20, min_chunk_size=10).chunk(
        clean_document("# Services\n\nWe deliver dependable software systems.")
    )

    assert len(chunks) == 1
    assert chunks[0].sequence == 0
    assert chunks[0].text == "# Services\n\nWe deliver dependable software systems."
    assert chunks[0].heading_path == ("Services",)
    assert chunks[0].character_count == len(chunks[0].text)


def test_document_exactly_at_boundary_produces_one_chunk():
    chunks = SemanticTextChunker(chunk_size=30, overlap=0, min_chunk_size=10).chunk(
        clean_document("x" * 30)
    )

    assert [len(chunk.text) for chunk in chunks] == [30]


def test_long_sections_split_at_paragraph_boundaries_with_stable_order():
    text = "# Services\n\n" + "\n\n".join(
        [
            "Discovery establishes a shared understanding of the problem.",
            "Delivery turns prioritised opportunities into reliable software.",
            "Evaluation measures outcomes and exposes operational risks.",
        ]
    )
    chunker = SemanticTextChunker(chunk_size=100, overlap=0, min_chunk_size=20)

    chunks = chunker.chunk(clean_document(text))

    assert len(chunks) == 3
    assert [chunk.sequence for chunk in chunks] == [0, 1, 2]
    assert "Discovery establishes" in chunks[0].text
    assert "Delivery turns" in chunks[1].text
    assert "Evaluation measures" in chunks[2].text
    assert all(chunk.text and len(chunk.text) <= 100 for chunk in chunks)


def test_sentence_then_safe_hard_split_are_used_for_oversized_paragraphs():
    sentence_text = "First sentence has useful context. Second sentence has more useful context. Third sentence closes the section."
    sentence_chunks = SemanticTextChunker(chunk_size=70, overlap=0, min_chunk_size=10).chunk(
        clean_document(sentence_text)
    )
    hard_chunks = SemanticTextChunker(chunk_size=30, overlap=0, min_chunk_size=10).chunk(
        clean_document("x" * 75)
    )

    assert sentence_chunks[0].text.endswith("context.")
    assert sentence_chunks[1].text.startswith("Second sentence")
    assert [len(chunk.text) for chunk in hard_chunks] == [30, 30, 15]
    assert "" not in [chunk.text for chunk in hard_chunks]


def test_hard_split_balances_a_small_tail_when_minimum_size_can_be_satisfied():
    chunks = SemanticTextChunker(chunk_size=30, overlap=0, min_chunk_size=20).chunk(
        clean_document("x" * 65)
    )

    assert [len(chunk.text) for chunk in chunks] == [22, 22, 21]


def test_overlap_reuses_bounded_context_without_repeating_a_full_chunk():
    text = "\n\n".join(
        [
            "Alpha paragraph contains enough useful context for readers.",
            "Beta paragraph contains another distinct and useful idea.",
            "Gamma paragraph completes this deliberately long document.",
        ]
    )
    chunks = SemanticTextChunker(chunk_size=90, overlap=25, min_chunk_size=10).chunk(
        clean_document(text)
    )

    assert len(chunks) >= 2
    assert all(len(chunk.text) <= 90 for chunk in chunks)
    assert chunks[1].text != chunks[0].text
    assert "context for readers." in chunks[1].text


def test_zero_overlap_does_not_repeat_prior_content():
    text = "Alpha content belongs first.\n\nBeta content belongs second."
    chunks = SemanticTextChunker(chunk_size=32, overlap=0, min_chunk_size=5).chunk(
        clean_document(text)
    )

    assert len(chunks) == 2
    assert "Alpha" not in chunks[1].text
    assert "Beta" not in chunks[0].text


def test_heading_context_tracks_nested_sections():
    text = "# Services\n\nOverview text.\n\n## AI Integration\n\nWe build grounded assistants for teams."
    chunks = SemanticTextChunker(chunk_size=55, overlap=0, min_chunk_size=5).chunk(
        clean_document(text)
    )

    assert chunks[-1].heading_path == ("Services", "AI Integration")
    assert "grounded assistants" in chunks[-1].text


def test_repeated_execution_produces_identical_ids_hashes_and_content():
    document = clean_document("# Guide\n\n" + "A useful sentence. " * 15)
    chunker = SemanticTextChunker(chunk_size=80, overlap=10, min_chunk_size=10)

    first = chunker.chunk(document)
    second = chunker.chunk(document)

    assert first == second
    assert len({chunk.id for chunk in first}) == len(first)
    assert len({chunk.content_hash for chunk in first}) == len(first)
    assert all(chunk.document_content_hash == "document-hash" for chunk in first)


def test_pathological_small_limits_terminate_without_empty_or_repeated_full_chunks():
    chunks = SemanticTextChunker(chunk_size=2, overlap=1, min_chunk_size=1).chunk(
        clean_document("abcdefghij")
    )

    assert 5 <= len(chunks) <= 10
    assert all(0 < len(chunk.text) <= 2 for chunk in chunks)
    assert all(left.text != right.text for left, right in zip(chunks, chunks[1:], strict=False))
