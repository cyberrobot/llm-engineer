from dataclasses import replace
from typing import Literal
from uuid import UUID

import pytest

from assistant.application.knowledge_persistence_service import (
    EmbeddingDimensionMismatchError,
    EmbeddingGenerationError,
    InvalidKnowledgeInputError,
    KnowledgePersistenceError,
    KnowledgePersistenceService,
)
from assistant.domain.content_processing_result import ContentProcessingResult
from assistant.domain.knowledge_chunk import KnowledgeChunk
from assistant.infrastructure.repositories.knowledge_persistence import (
    KnowledgeDocumentRecord,
    KnowledgeWriteResult,
    PersistedKnowledgeChunk,
)


def chunk(
    *,
    source_url: str = "https://example.com/guide",
    sequence: int = 0,
    text: str = "Discovery workshops align teams.",
    document_hash: str = "document-v1",
) -> KnowledgeChunk:
    return KnowledgeChunk(
        id=UUID(int=sequence + 1),
        source_url=source_url,
        title="Discovery guide",
        sequence=sequence,
        text=text,
        content_hash=f"chunk-{document_hash}-{sequence}",
        document_content_hash=document_hash,
        heading_path=("Discovery",),
        character_count=len(text),
    )


def result(*chunks: KnowledgeChunk) -> ContentProcessingResult:
    urls = {item.source_url for item in chunks}
    return ContentProcessingResult(
        documents_received=len(urls),
        documents_processed=len(urls),
        documents_skipped=0,
        chunks_created=len(chunks),
        chunks=list(chunks),
        warnings=[],
        duration_ms=1,
    )


class FakeEmbeddingProvider:
    def __init__(self, vectors: list[list[float]] | None = None) -> None:
        self.vectors = vectors
        self.calls: list[list[str]] = []
        self.error: Exception | None = None

    def generate_embeddings(self, *, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        if self.error:
            raise self.error
        if self.vectors is not None:
            output, self.vectors = self.vectors, []
            return output
        return [[float(len(text)), float(index), 1.0] for index, text in enumerate(texts)]


class FakeKnowledgePersistenceRepository:
    def __init__(self) -> None:
        self.documents: dict[str, KnowledgeDocumentRecord] = {}
        self.chunks: dict[str, list[PersistedKnowledgeChunk]] = {}
        self.writes: list[tuple[KnowledgeDocumentRecord, list[PersistedKnowledgeChunk]]] = []
        self.error: Exception | None = None

    def find_document_by_source_url(self, source_url: str) -> KnowledgeDocumentRecord | None:
        return self.documents.get(source_url)

    def replace_document(
        self,
        document: KnowledgeDocumentRecord,
        chunks: list[PersistedKnowledgeChunk],
    ) -> KnowledgeWriteResult:
        if self.error:
            raise self.error
        existing = self.documents.get(document.source_url)
        if existing and existing.content_hash == document.content_hash:
            return KnowledgeWriteResult(
                action="unchanged",
                document_id=existing.id,
                previous_chunk_count=len(self.chunks[document.source_url]),
            )
        previous_count = len(self.chunks.get(document.source_url, []))
        action: Literal["created", "updated"] = "updated" if existing else "created"
        self.documents[document.source_url] = document
        self.chunks[document.source_url] = list(chunks)
        self.writes.append((document, list(chunks)))
        return KnowledgeWriteResult(
            action=action,
            document_id=document.id,
            previous_chunk_count=previous_count,
        )

    def update_document_metadata(
        self,
        document: KnowledgeDocumentRecord,
    ) -> KnowledgeWriteResult:
        existing = self.documents[document.source_url]
        current_chunks = self.chunks[document.source_url]
        self.documents[document.source_url] = document
        self.chunks[document.source_url] = [
            replace(item, access_roles=document.access_roles) for item in current_chunks
        ]
        return KnowledgeWriteResult(
            action="updated",
            document_id=existing.id,
            previous_chunk_count=len(current_chunks),
        )


def service(
    provider: FakeEmbeddingProvider | None = None,
    repository: FakeKnowledgePersistenceRepository | None = None,
    *,
    batch_size: int = 10,
) -> tuple[
    KnowledgePersistenceService,
    FakeEmbeddingProvider,
    FakeKnowledgePersistenceRepository,
]:
    provider = provider or FakeEmbeddingProvider()
    repository = repository or FakeKnowledgePersistenceRepository()
    return (
        KnowledgePersistenceService(
            provider,
            repository,
            embedding_dimensions=3,
            embedding_batch_size=batch_size,
        ),
        provider,
        repository,
    )


def test_persists_new_document_in_sequence_order_with_roles_and_accurate_counts():
    persistence, provider, repository = service()

    outcome = persistence.persist(
        result(
            chunk(sequence=1, text="Second chunk"),
            chunk(sequence=0, text="First chunk"),
        ),
        access_roles=("user", "manager"),
    )

    assert provider.calls == [["First chunk", "Second chunk"]]
    stored_document, stored_chunks = repository.writes[0]
    assert stored_document.source_url == "https://example.com/guide"
    assert stored_document.access_roles == ("user", "manager")
    assert [item.sequence for item in stored_chunks] == [0, 1]
    assert [item.text for item in stored_chunks] == ["First chunk", "Second chunk"]
    assert all(item.document_id == stored_document.id for item in stored_chunks)
    assert all(item.access_roles == ("user", "manager") for item in stored_chunks)
    assert outcome.documents_created == 1
    assert outcome.documents_updated == 0
    assert outcome.documents_unchanged == 0
    assert outcome.chunks_created == 2
    assert outcome.chunks_removed == 0
    assert outcome.embeddings_generated == 2


def test_identical_content_is_a_no_op_without_new_embeddings_or_writes():
    persistence, provider, repository = service()
    processed = result(chunk(sequence=0), chunk(sequence=1, text="Delivery reduces risk."))

    first = persistence.persist(processed)
    second = persistence.persist(processed)

    assert first.documents_created == 1
    assert second.documents_unchanged == 1
    assert second.chunks_unchanged == 2
    assert second.chunks_created == 0
    assert second.embeddings_generated == 0
    assert len(provider.calls) == 1
    assert len(repository.writes) == 1


def test_identical_content_with_changed_roles_updates_metadata_without_new_embeddings():
    persistence, provider, repository = service()
    processed = result(chunk())
    persistence.persist(processed, access_roles=("user",))

    changed_roles = persistence.persist(processed, access_roles=("manager",))

    assert changed_roles.documents_updated == 1
    assert changed_roles.chunks_updated == 1
    assert changed_roles.embeddings_generated == 0
    assert len(provider.calls) == 1
    assert repository.documents["https://example.com/guide"].access_roles == ("manager",)
    assert repository.chunks["https://example.com/guide"][0].access_roles == ("manager",)


def test_changed_document_replaces_obsolete_chunks_atomically():
    persistence, provider, repository = service()
    persistence.persist(result(chunk(sequence=0), chunk(sequence=1, text="Stale knowledge")))

    changed = result(chunk(sequence=0, text="Current knowledge", document_hash="document-v2"))
    outcome = persistence.persist(changed)

    assert outcome.documents_updated == 1
    assert outcome.chunks_created == 1
    assert outcome.chunks_removed == 2
    assert outcome.embeddings_generated == 1
    assert [item.text for item in repository.chunks["https://example.com/guide"]] == [
        "Current knowledge"
    ]
    assert provider.calls[-1] == ["Current knowledge"]


def test_batches_embeddings_without_changing_chunk_order():
    persistence, provider, repository = service(batch_size=2)
    processed = result(
        chunk(sequence=2, text="Three"),
        chunk(sequence=0, text="One"),
        chunk(sequence=1, text="Two"),
    )

    persistence.persist(processed)

    assert provider.calls == [["One", "Two"], ["Three"]]
    assert [item.sequence for item in repository.writes[0][1]] == [0, 1, 2]


@pytest.mark.parametrize(
    ("processed", "message"),
    [
        (result(), "at least one chunk"),
        (result(replace(chunk(), text="")), "text must not be empty"),
        (result(replace(chunk(), content_hash="")), "content hash must not be empty"),
        (
            result(replace(chunk(), document_content_hash="")),
            "document content hash must not be empty",
        ),
        (result(chunk(sequence=0), chunk(sequence=0, text="duplicate")), "duplicate sequence"),
        (
            result(
                chunk(sequence=0), replace(chunk(sequence=1), content_hash="chunk-document-v1-0")
            ),
            "duplicate content hash",
        ),
    ],
)
def test_rejects_invalid_input_before_embedding_or_persistence(processed, message):
    persistence, provider, repository = service()

    with pytest.raises(InvalidKnowledgeInputError, match=message):
        persistence.persist(processed)

    assert provider.calls == []
    assert repository.writes == []


def test_rejects_empty_access_roles_before_embedding_or_persistence():
    persistence, provider, repository = service()

    with pytest.raises(InvalidKnowledgeInputError, match="At least one access role"):
        persistence.persist(result(chunk()), access_roles=())

    assert provider.calls == []
    assert repository.writes == []


@pytest.mark.parametrize(
    "vectors",
    [
        [],
        [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]],
    ],
)
def test_rejects_embedding_count_mismatch_without_persisting(vectors):
    provider = FakeEmbeddingProvider(vectors)
    persistence, _, repository = service(provider)

    with pytest.raises(EmbeddingGenerationError, match="number of embeddings"):
        persistence.persist(result(chunk()))

    assert repository.writes == []


def test_rejects_embedding_dimension_mismatch_without_persisting():
    provider = FakeEmbeddingProvider([[1.0, 2.0]])
    persistence, _, repository = service(provider)

    with pytest.raises(EmbeddingDimensionMismatchError, match="expected 3"):
        persistence.persist(result(chunk()))

    assert repository.writes == []


def test_maps_embedding_provider_failure_without_persisting_or_logging_details(caplog):
    provider = FakeEmbeddingProvider()
    provider.error = RuntimeError("provider secret")
    persistence, _, repository = service(provider)

    with pytest.raises(EmbeddingGenerationError) as raised:
        persistence.persist(result(chunk()))

    assert "provider secret" not in str(raised.value)
    assert "provider secret" not in caplog.text
    assert repository.writes == []


def test_maps_repository_failure_at_application_boundary():
    repository = FakeKnowledgePersistenceRepository()
    repository.error = RuntimeError("database credentials")
    persistence, _, _ = service(repository=repository)

    with pytest.raises(KnowledgePersistenceError) as raised:
        persistence.persist(result(chunk()))

    assert "database credentials" not in str(raised.value)
