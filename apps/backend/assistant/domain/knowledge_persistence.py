from contextlib import AbstractContextManager
from dataclasses import dataclass
from enum import Enum
from typing import Literal, Protocol
from uuid import UUID

from assistant.domain.assistant import DocumentRetrievalState


@dataclass(frozen=True, slots=True)
class KnowledgeDocumentRecord:
    id: str
    assistant_id: UUID
    source_url: str
    title: str | None
    content_hash: str
    access_roles: tuple[str, ...]
    retrieval_state: DocumentRetrievalState = DocumentRetrievalState.enabled


@dataclass(frozen=True, slots=True)
class PersistedKnowledgeChunk:
    id: str
    assistant_id: UUID
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


class KnowledgePersistenceWriteConflict(RuntimeError):
    """Raised when the active document changed after its replacement was prepared."""


class PersistenceMode(str, Enum):
    new = "NEW"
    reindex = "REINDEX"
    recovery = "RECOVERY"


@dataclass(frozen=True, slots=True)
class PersistIngestionResult:
    """Immutable command for the final database-only ingestion boundary."""

    ingestion_job_id: UUID
    document_id: str
    prepared: "PreparedKnowledge"
    mode: PersistenceMode
    command_hash: str
    source_fingerprint: str | None = None


@dataclass(frozen=True, slots=True)
class CommittedIngestionResult:
    ingestion_job_id: UUID
    document_id: str
    command_hash: str
    result: "KnowledgePersistenceResult"


class KnowledgePersistenceTransaction(Protocol):
    def find_committed_result(self, ingestion_job_id: UUID) -> CommittedIngestionResult | None: ...

    def lock_ingestion_job(self, ingestion_job_id: UUID, document_id: str) -> None: ...

    def replace_document(
        self,
        document: KnowledgeDocumentRecord,
        chunks: list[PersistedKnowledgeChunk],
        *,
        ingestion_job_id: UUID | None = None,
        expected_previous_content_hash: str | None = None,
        force_replace: bool = False,
    ) -> KnowledgeWriteResult: ...

    def update_document_metadata(
        self,
        document: KnowledgeDocumentRecord,
    ) -> KnowledgeWriteResult: ...

    def record_committed_result(
        self, command: PersistIngestionResult, result: "KnowledgePersistenceResult"
    ) -> None: ...


class KnowledgePersistenceRepository(Protocol):
    """Atomic document-level write boundary for processed knowledge."""

    def find_document_by_source_url(
        self, source_url: str, *, assistant_id: UUID
    ) -> KnowledgeDocumentRecord | None:
        """Return the current website document identity, if present."""

    def transaction(self) -> AbstractContextManager[KnowledgePersistenceTransaction]:
        """Open the single caller-owned transaction for final persistence."""

    def replace_document(
        self,
        document: KnowledgeDocumentRecord,
        chunks: list[PersistedKnowledgeChunk],
        *,
        ingestion_job_id: UUID | None = None,
        expected_previous_content_hash: str | None = None,
        force_replace: bool = False,
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


@dataclass(frozen=True, slots=True)
class PreparedKnowledgeDocument:
    document: KnowledgeDocumentRecord
    chunks: tuple[PersistedKnowledgeChunk, ...]
    disposition: Literal["replace", "metadata", "unchanged"]
    previous_chunk_count: int
    expected_previous_content_hash: str | None = None


@dataclass(frozen=True, slots=True)
class PreparedKnowledge:
    documents: tuple[PreparedKnowledgeDocument, ...]
    chunks_received: int
    embeddings_generated: int
    embedding_duration_ms: int
    database_duration_ms: int
