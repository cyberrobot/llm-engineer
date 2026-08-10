import logging
from datetime import datetime, timezone

import pytest

from assistant.application.content_processing_service import (
    ContentProcessingError,
    ContentProcessingService,
    NoProcessableContentError,
)
from assistant.application.content_stage_errors import (
    RecoverableContentExtractionError,
    RecoverableTextChunkingError,
    RecoverableTextCleaningError,
)
from assistant.application.ports.content_extractor import ContentExtractor
from assistant.application.ports.text_chunker import TextChunker
from assistant.application.ports.text_cleaner import TextCleaner
from assistant.domain.clean_document import CleanDocument
from assistant.domain.extracted_document import ExtractedDocument
from assistant.domain.knowledge_chunk import KnowledgeChunk
from assistant.domain.website_document import WebsiteDocument

RETRIEVED_AT = datetime(2026, 7, 29, 9, 0, tzinfo=timezone.utc)


def raw(url: str, html: str = "<main>Useful page content.</main>") -> WebsiteDocument:
    return WebsiteDocument(url, 200, "text/html", html, None, RETRIEVED_AT)


def extracted(document: WebsiteDocument) -> ExtractedDocument:
    return ExtractedDocument(document.url, None, [], "Useful page content.", document.retrieved_at)


def cleaned(document: ExtractedDocument) -> CleanDocument:
    return CleanDocument(
        document.source_url,
        document.title,
        document.text,
        "document-hash",
        document.retrieved_at,
    )


def chunk(document: CleanDocument) -> KnowledgeChunk:
    return KnowledgeChunk.create(document=document, sequence=0, text=document.text)


class FakeExtractor(ContentExtractor):
    def __init__(self, failures=(), empty=(), unexpected=()):
        self.failures = set(failures)
        self.empty = set(empty)
        self.unexpected = set(unexpected)
        self.seen = []

    def extract(self, document):
        self.seen.append(document.url)
        if document.url in self.failures:
            raise RecoverableContentExtractionError("EXTRACTION SECRET")
        if document.url in self.unexpected:
            raise TypeError("EXTRACTION PROGRAMMING SECRET")
        if document.url in self.empty:
            return None
        return extracted(document)


class FakeCleaner(TextCleaner):
    def __init__(self, failures=(), empty=(), unexpected=()):
        self.failures = set(failures)
        self.empty = set(empty)
        self.unexpected = set(unexpected)

    def clean(self, document):
        if document.source_url in self.failures:
            raise RecoverableTextCleaningError("CLEANING SECRET")
        if document.source_url in self.unexpected:
            raise TypeError("CLEANING PROGRAMMING SECRET")
        if document.source_url in self.empty:
            return None
        return cleaned(document)


class FakeChunker(TextChunker):
    def __init__(self, failures=(), empty=(), unexpected=()):
        self.failures = set(failures)
        self.empty = set(empty)
        self.unexpected = set(unexpected)

    def chunk(self, document):
        if document.source_url in self.failures:
            raise RecoverableTextChunkingError("CHUNKING SECRET")
        if document.source_url in self.unexpected:
            raise TypeError("CHUNKING PROGRAMMING SECRET")
        if document.source_url in self.empty:
            return []
        return [chunk(document)]


def test_processes_multiple_documents_in_input_and_chunk_order(caplog):
    documents = [raw("https://example.com/one"), raw("https://example.com/two")]
    service = ContentProcessingService(FakeExtractor(), FakeCleaner(), FakeChunker())

    with caplog.at_level(logging.INFO):
        result = service.process(documents)

    assert result.documents_received == 2
    assert result.documents_processed == 2
    assert result.documents_skipped == 0
    assert result.chunks_created == 2
    assert [item.source_url for item in result.chunks] == [document.url for document in documents]
    assert [item.sequence for item in result.chunks] == [0, 0]
    assert result.warnings == []
    assert result.duration_ms >= 0
    completion = next(
        record for record in caplog.records if record.getMessage() == "Content processing completed"
    )
    assert completion.documents_received == 2
    assert completion.documents_processed == 2
    assert completion.documents_skipped == 0
    assert completion.chunks_created == 2
    assert not any("Useful page content" in record.getMessage() for record in caplog.records)


@pytest.mark.parametrize(
    ("stage", "expected_code"),
    [
        ("extractor", "extraction_failed"),
        ("cleaner", "cleaning_failed"),
        ("chunker", "chunking_failed"),
    ],
)
def test_recoverable_stage_failure_warns_and_does_not_stop_valid_documents(
    stage, expected_code, caplog
):
    bad = "https://example.com/bad"
    extractor = FakeExtractor(failures=[bad] if stage == "extractor" else [])
    cleaner = FakeCleaner(failures=[bad] if stage == "cleaner" else [])
    chunker = FakeChunker(failures=[bad] if stage == "chunker" else [])
    service = ContentProcessingService(extractor, cleaner, chunker)

    with caplog.at_level(logging.WARNING):
        result = service.process([raw(bad), raw("https://example.com/good")])

    assert result.documents_processed == 1
    assert result.documents_skipped == 1
    assert result.chunks_created == 1
    assert [(warning.source_url, warning.code) for warning in result.warnings] == [
        (bad, expected_code)
    ]
    assert "SECRET" not in caplog.text
    assert all("SECRET" not in warning.message for warning in result.warnings)


@pytest.mark.parametrize(
    ("component", "stage"),
    [("extractor", "extraction"), ("cleaner", "cleaning"), ("chunker", "chunking")],
)
def test_unexpected_stage_failure_aborts_with_safe_chained_error(component, stage, caplog):
    bad = "https://user:password@example.com/private?token=secret#fragment"
    extractor = FakeExtractor(unexpected=[bad] if component == "extractor" else [])
    cleaner = FakeCleaner(unexpected=[bad] if component == "cleaner" else [])
    chunker = FakeChunker(unexpected=[bad] if component == "chunker" else [])
    service = ContentProcessingService(extractor, cleaner, chunker)

    with caplog.at_level(logging.ERROR), pytest.raises(ContentProcessingError) as raised:
        service.process([raw(bad), raw("https://example.com/not-processed")])

    assert isinstance(raised.value.__cause__, TypeError)
    assert str(raised.value) == f"Unexpected content-processing failure during {stage}."
    assert "PROGRAMMING SECRET" not in caplog.text
    assert "password" not in caplog.text
    assert "token" not in caplog.text
    failure_record = next(
        record
        for record in caplog.records
        if record.getMessage() == "Unexpected content-processing failure"
    )
    assert failure_record.stage == stage
    assert failure_record.source == "https://example.com"
    assert failure_record.exception_type == "TypeError"
    assert extractor.seen == [bad]


def test_arbitrary_value_error_is_not_treated_as_a_recoverable_page_failure():
    class InvalidExtractor(ContentExtractor):
        def extract(self, document):
            raise ValueError("unexpected invariant failure")

    service = ContentProcessingService(InvalidExtractor(), FakeCleaner(), FakeChunker())

    with pytest.raises(ContentProcessingError) as raised:
        service.process([raw("https://example.com/bad")])

    assert isinstance(raised.value.__cause__, ValueError)


@pytest.mark.parametrize(
    ("extract_empty", "clean_empty", "chunk_empty", "expected_code"),
    [
        (True, False, False, "no_meaningful_content"),
        (False, True, False, "content_below_minimum"),
        (False, False, True, "no_chunks_created"),
    ],
)
def test_recoverable_empty_stage_result_is_counted_as_skipped(
    extract_empty, clean_empty, chunk_empty, expected_code
):
    skipped = "https://example.com/skipped"
    service = ContentProcessingService(
        FakeExtractor(empty=[skipped] if extract_empty else []),
        FakeCleaner(empty=[skipped] if clean_empty else []),
        FakeChunker(empty=[skipped] if chunk_empty else []),
    )

    result = service.process([raw(skipped), raw("https://example.com/good")])

    assert result.documents_skipped == 1
    assert [warning.code for warning in result.warnings] == [expected_code]


def test_all_unusable_documents_raise_error_with_aggregated_warnings_and_counters():
    urls = ["https://example.com/empty", "https://example.com/broken"]
    service = ContentProcessingService(
        FakeExtractor(empty=[urls[0]], failures=[urls[1]]), FakeCleaner(), FakeChunker()
    )

    with pytest.raises(NoProcessableContentError) as raised:
        service.process([raw(url) for url in urls])

    result = raised.value.result
    assert result.documents_received == 2
    assert result.documents_processed == 0
    assert result.documents_skipped == 2
    assert result.chunks_created == 0
    assert [warning.code for warning in result.warnings] == [
        "no_meaningful_content",
        "extraction_failed",
    ]


def test_empty_input_raises_no_processable_content_error():
    service = ContentProcessingService(FakeExtractor(), FakeCleaner(), FakeChunker())

    with pytest.raises(NoProcessableContentError) as raised:
        service.process([])

    assert raised.value.result.documents_received == 0
    assert raised.value.result.documents_skipped == 0
