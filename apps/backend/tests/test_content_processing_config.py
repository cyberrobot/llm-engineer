import pytest

from assistant.api.dependencies import (
    get_content_extractor,
    get_content_processing_service,
    get_text_chunker,
    get_text_cleaner,
)
from assistant.application.content_processing_service import ContentProcessingService
from assistant.infrastructure.ingestion.html_content_extractor import HtmlContentExtractor
from assistant.infrastructure.ingestion.normalising_text_cleaner import NormalisingTextCleaner
from assistant.infrastructure.ingestion.semantic_text_chunker import SemanticTextChunker
from core.config import ContentProcessingSettings, get_content_processing_settings


def test_content_processing_settings_are_character_based_and_environment_driven(monkeypatch):
    monkeypatch.setenv("INGESTION_CHUNK_SIZE_CHARACTERS", "900")
    monkeypatch.setenv("INGESTION_CHUNK_OVERLAP_CHARACTERS", "120")
    monkeypatch.setenv("INGESTION_MIN_CHUNK_SIZE_CHARACTERS", "80")
    monkeypatch.setenv("INGESTION_MIN_DOCUMENT_LENGTH_CHARACTERS", "140")

    assert get_content_processing_settings() == ContentProcessingSettings(
        chunk_size_characters=900,
        chunk_overlap_characters=120,
        min_chunk_size_characters=80,
        min_document_length_characters=140,
    )


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("INGESTION_CHUNK_SIZE_CHARACTERS", "0"),
        ("INGESTION_CHUNK_OVERLAP_CHARACTERS", "-1"),
        ("INGESTION_MIN_CHUNK_SIZE_CHARACTERS", "0"),
        ("INGESTION_MIN_DOCUMENT_LENGTH_CHARACTERS", "-1"),
    ],
)
def test_content_processing_settings_reject_invalid_individual_values(monkeypatch, name, value):
    monkeypatch.setenv(name, value)

    with pytest.raises(ValueError, match=name):
        get_content_processing_settings()


def test_content_processing_settings_reject_overlap_equal_to_or_above_chunk_size(monkeypatch):
    monkeypatch.setenv("INGESTION_CHUNK_SIZE_CHARACTERS", "100")
    monkeypatch.setenv("INGESTION_CHUNK_OVERLAP_CHARACTERS", "100")

    with pytest.raises(ValueError, match="INGESTION_CHUNK_OVERLAP_CHARACTERS"):
        get_content_processing_settings()


def test_dependency_injection_registers_ports_and_processing_service():
    get_content_extractor.cache_clear()
    get_text_cleaner.cache_clear()
    get_text_chunker.cache_clear()

    extractor = get_content_extractor()
    cleaner = get_text_cleaner()
    chunker = get_text_chunker()
    service = get_content_processing_service(extractor, cleaner, chunker)

    assert isinstance(extractor, HtmlContentExtractor)
    assert isinstance(cleaner, NormalisingTextCleaner)
    assert isinstance(chunker, SemanticTextChunker)
    assert isinstance(service, ContentProcessingService)
