from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from assistant.application.ingestion_pipeline import IngestionPipelineContext
from assistant.application.ingestion_pipeline_context import WebsiteIngestionContextFactory
from assistant.application.ingestion_pipeline_steps import (
    ChunkIngestionStep,
    EmbedIngestionStep,
    ParseIngestionStep,
    PersistIngestionStep,
)
from assistant.domain.content_processing_result import ContentProcessingResult
from assistant.domain.document_ingestion_job import IngestionStep
from assistant.domain.knowledge_persistence import PreparedKnowledge
from assistant.domain.website_document import WebsiteDocument
from assistant.infrastructure.repositories.document_ingestion_job import (
    IngestionDocumentSource,
    InMemoryDocumentIngestionJobRepository,
)


def context() -> IngestionPipelineContext:
    return IngestionPipelineContext(
        uuid4(), "document-1", metadata={"source_url": "https://example.com"}
    )


class FakeLoader:
    def __init__(self) -> None:
        self.error: Exception | None = None

    def load(self, url: str) -> list[WebsiteDocument]:
        assert url == "https://example.com"
        if self.error:
            raise self.error
        return [
            WebsiteDocument(
                url, 200, "text/html", "<p>Useful</p>", None, datetime.now(timezone.utc)
            )
        ]


class FakeProcessor:
    def process(self, documents):
        assert len(documents) == 1
        return ContentProcessingResult(1, 1, 0, 0, [], [], 1)


@dataclass
class FakePersistence:
    prepared: PreparedKnowledge = PreparedKnowledge((), 0, 0, 0, 0)
    prepare_calls: int = 0
    persist_calls: int = 0

    def prepare(self, chunks, *, access_roles=("user",)):
        assert isinstance(chunks, ContentProcessingResult)
        assert access_roles == ("manager",)
        self.prepare_calls += 1
        return self.prepared

    def persist_prepared(self, prepared):
        assert prepared is self.prepared
        self.persist_calls += 1
        return "persisted"


def test_concrete_steps_transfer_typed_context_without_crossing_responsibilities():
    state = context()
    state.metadata["access_roles"] = ("manager",)
    loader = FakeLoader()
    processor = FakeProcessor()
    persistence = FakePersistence()

    assert ParseIngestionStep(loader).execute(state).succeeded
    assert state.parsed_document is not None
    assert ChunkIngestionStep(processor).execute(state).succeeded
    assert state.chunks is not None
    assert persistence.prepare_calls == persistence.persist_calls == 0
    assert EmbedIngestionStep(persistence).execute(state).succeeded
    assert state.embeddings is persistence.prepared
    assert persistence.prepare_calls == 1
    assert persistence.persist_calls == 0
    assert PersistIngestionStep(persistence).execute(state).succeeded
    assert persistence.persist_calls == 1
    assert state.metadata["persistence_result"] == "persisted"


def test_steps_return_safe_failures_for_missing_input_and_dependency_errors():
    state = context()
    loader = FakeLoader()
    loader.error = RuntimeError("upstream credential secret")

    parse_result = ParseIngestionStep(loader).execute(state)
    chunk_result = ChunkIngestionStep(FakeProcessor()).execute(context())
    embed_result = EmbedIngestionStep(FakePersistence()).execute(context())
    persist_result = PersistIngestionStep(FakePersistence()).execute(context())

    assert parse_result.failure_code == "document_parse_failed"
    assert "secret" not in (parse_result.failure_message or "")
    assert chunk_result.failure_code == "missing_parsed_document"
    assert embed_result.failure_code == "missing_ingestion_chunks"
    assert persist_result.failure_code == "missing_ingestion_embeddings"


def test_context_factory_reconstructs_transient_inputs_for_a_seeded_checkpoint():
    source = IngestionDocumentSource("https://example.com", ("manager",))
    repository = InMemoryDocumentIngestionJobRepository(document_sources={"document-1": source})
    persistence = FakePersistence()

    rebuilt = WebsiteIngestionContextFactory(
        repository, FakeLoader(), FakeProcessor(), persistence
    )(uuid4(), "document-1", IngestionStep.embed)

    assert rebuilt.parsed_document is not None
    assert rebuilt.chunks is not None
    assert rebuilt.embeddings is persistence.prepared
    assert persistence.prepare_calls == 1
