from datetime import datetime, timezone

from assistant.domain.extracted_document import ExtractedDocument
from assistant.infrastructure.ingestion.normalising_text_cleaner import NormalisingTextCleaner

RETRIEVED_AT = datetime(2026, 7, 29, 9, 0, tzinfo=timezone.utc)


def extracted(text: str) -> ExtractedDocument:
    return ExtractedDocument(
        source_url="https://example.com/guide",
        title=" Guide ",
        headings=["Guide"],
        text=text,
        retrieved_at=RETRIEVED_AT,
    )


def test_clean_normalises_unicode_line_endings_spacing_and_control_characters():
    cleaner = NormalisingTextCleaner(min_document_length=1)

    result = cleaner.clean(extracted("# Cafe\u0301\r\n\r\nA\u200b  useful\tguide.\x00"))

    assert result is not None
    assert result.text == "# Café\n\nA useful guide."
    assert result.title == "Guide"


def test_clean_preserves_headings_lists_and_paragraphs_while_removing_adjacent_duplicates():
    cleaner = NormalisingTextCleaner(min_document_length=1)
    text = (
        "# Services\n\nParagraph one.\nParagraph one.\n\n\n\n- Discovery\n- Discovery\n- Delivery"
    )

    result = cleaner.clean(extracted(text))

    assert result is not None
    assert result.text == "# Services\n\nParagraph one.\n\n- Discovery\n- Delivery"


def test_clean_returns_none_for_empty_whitespace_or_below_minimum_content():
    cleaner = NormalisingTextCleaner(min_document_length=20)

    assert cleaner.clean(extracted("")) is None
    assert cleaner.clean(extracted(" \r\n\t ")) is None
    assert cleaner.clean(extracted("# Home\n\nTiny")) is None


def test_content_hash_is_sha256_of_cleaned_text_and_is_deterministic():
    cleaner = NormalisingTextCleaner(min_document_length=1)

    first = cleaner.clean(extracted("Useful   text."))
    second = cleaner.clean(extracted("Useful text.\r\n"))

    assert first is not None and second is not None
    assert first.text == second.text == "Useful text."
    assert first.content_hash == second.content_hash
    assert first.content_hash == "26dcb8f6348376d9e1b20b0a53a06d8d2b031e1843c7156339b8bc29409ba7ae"
