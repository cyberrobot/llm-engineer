from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from assistant.domain.assistant import DocumentRetrievalState
from assistant.domain.document_ingestion_job import DocumentIngestionJob
from assistant.domain.knowledge_source import KnowledgeSource


class KnowledgeSourceConflict(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class KnowledgeSourceAggregate:
    total: int
    enabled: int


class KnowledgeSourceTransaction(Protocol):
    def create(
        self,
        source: KnowledgeSource,
        job: DocumentIngestionJob,
        request_hash: str,
        idempotency_key: str | None,
    ) -> tuple[KnowledgeSource, DocumentIngestionJob]: ...
    def update_retrieval_state(
        self, assistant_id: UUID, source_id: UUID, state: DocumentRetrievalState
    ) -> KnowledgeSource | None: ...
    def delete(self, assistant_id: UUID, source_id: UUID) -> bool: ...
    def reingest(
        self,
        assistant_id: UUID,
        source_id: UUID,
        job: DocumentIngestionJob,
        request_hash: str,
        idempotency_key: str | None,
    ) -> tuple[KnowledgeSource, DocumentIngestionJob, bool]: ...


class KnowledgeSourceRepository(Protocol):
    def aggregate_counts(self) -> KnowledgeSourceAggregate: ...
    def transaction(self) -> AbstractContextManager[KnowledgeSourceTransaction]: ...
    def get(self, assistant_id: UUID, source_id: UUID) -> KnowledgeSource | None: ...
    def list(
        self, assistant_id: UUID, *, limit: int, offset: int
    ) -> tuple[list[KnowledgeSource], int]: ...
    def latest_job(self, document_id: str) -> DocumentIngestionJob | None: ...
    def active_job(self, document_id: str) -> DocumentIngestionJob | None: ...
    def create_job(self, job: DocumentIngestionJob) -> DocumentIngestionJob: ...
    def find_creation(self, assistant_id: UUID, key: str) -> tuple[KnowledgeSource, str] | None: ...
    def find_by_url(self, assistant_id: UUID, normalized_url: str) -> KnowledgeSource | None: ...
