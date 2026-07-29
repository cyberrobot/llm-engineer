from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass(frozen=True, slots=True)
class KnowledgeDocumentRecord:
    id: str
    source_url: str
    title: str | None
    content_hash: str
    access_roles: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PersistedKnowledgeChunk:
    id: str
    document_id: str
    sequence: int
    text: str
    content_hash: str
    embedding: tuple[float, ...]
    heading_path: tuple[str, ...]
    access_roles: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class KnowledgeWriteResult:
    action: Literal["created", "updated", "unchanged"]
    document_id: str
    previous_chunk_count: int


class KnowledgePersistenceRepository(Protocol):
    """Atomic document-level write boundary for processed knowledge."""

    def find_document_by_source_url(self, source_url: str) -> KnowledgeDocumentRecord | None:
        """Return the current website document identity, if present."""

    def replace_document(
        self,
        document: KnowledgeDocumentRecord,
        chunks: list[PersistedKnowledgeChunk],
    ) -> KnowledgeWriteResult:
        """Create or atomically replace one document and all of its chunks."""

    def update_document_metadata(
        self,
        document: KnowledgeDocumentRecord,
    ) -> KnowledgeWriteResult:
        """Update title and access roles without rewriting unchanged vectors."""


@dataclass(frozen=True, slots=True)
class KnowledgePersistenceResult:
    documents_received: int
    documents_created: int
    documents_updated: int
    documents_unchanged: int
    chunks_received: int
    chunks_created: int
    chunks_updated: int
    chunks_unchanged: int
    chunks_removed: int
    embeddings_generated: int
    duration_ms: int
    embedding_duration_ms: int = 0
    database_duration_ms: int = 0
