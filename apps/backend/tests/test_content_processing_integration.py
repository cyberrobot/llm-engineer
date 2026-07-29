from datetime import datetime, timezone
from pathlib import Path

from assistant.application.content_processing_service import ContentProcessingService
from assistant.domain.website_document import WebsiteDocument
from assistant.infrastructure.ingestion.html_content_extractor import HtmlContentExtractor
from assistant.infrastructure.ingestion.normalising_text_cleaner import NormalisingTextCleaner
from assistant.infrastructure.ingestion.semantic_text_chunker import SemanticTextChunker

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "content_processing"
RETRIEVED_AT = datetime(2026, 7, 29, 9, 0, tzinfo=timezone.utc)


def website_load_result() -> list[WebsiteDocument]:
    return [
        WebsiteDocument(
            url=f"https://example.com/{name.removesuffix('.html')}",
            status_code=200,
            content_type="text/html",
            html=(FIXTURE_DIR / name).read_text(),
            title=None,
            retrieved_at=RETRIEVED_AT,
        )
        for name in ["business_homepage.html", "service_page.html", "low_value.html"]
    ]


def test_raw_website_documents_are_transformed_to_clean_ordered_chunks_without_side_effects():
    service = ContentProcessingService(
        HtmlContentExtractor(),
        NormalisingTextCleaner(min_document_length=40),
        SemanticTextChunker(chunk_size=120, overlap=20, min_chunk_size=20),
    )

    result = service.process(website_load_result())

    assert result.documents_received == 3
    assert result.documents_processed == 2
    assert result.documents_skipped == 1
    assert result.chunks_created == len(result.chunks) >= 3
    assert [warning.code for warning in result.warnings] == ["no_meaningful_content"]
    assert result.chunks[0].source_url.endswith("business_homepage")
    assert result.chunks[-1].source_url.endswith("service_page")
    assert all(chunk.text.strip() == chunk.text and chunk.text for chunk in result.chunks)
    assert all("SCRIPT SECRET" not in chunk.text for chunk in result.chunks)
    assert all(not hasattr(chunk, "embedding") for chunk in result.chunks)
