import logging
from collections import defaultdict
from collections.abc import Sequence
from time import monotonic
from uuid import NAMESPACE_URL, uuid5

from assistant.application.ports.embedding_provider import EmbeddingProvider
from assistant.domain.content_processing_result import ContentProcessingResult
from assistant.domain.knowledge_chunk import KnowledgeChunk
from assistant.domain.knowledge_persistence import (
    KnowledgeDocumentRecord,
    KnowledgePersistenceRepository,
    KnowledgePersistenceResult,
    PersistedKnowledgeChunk,
    PreparedKnowledge,
    PreparedKnowledgeDocument,
)

logger = logging.getLogger(__name__)


class KnowledgePersistenceError(RuntimeError):
    """Base error exposed by the knowledge-persistence application boundary."""


class InvalidKnowledgeInputError(KnowledgePersistenceError):
    """Raised before side effects when processed knowledge violates its contract."""


class EmbeddingGenerationError(KnowledgePersistenceError):
    """Raised when embeddings cannot be generated or violate provider ordering."""


class EmbeddingDimensionMismatchError(EmbeddingGenerationError):
    """Raised when a provider vector cannot fit the configured retrieval schema."""


class KnowledgePersistenceService:
    """Persist Chunk 7C output with document-level idempotency and atomic writes."""

    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        repository: KnowledgePersistenceRepository,
        *,
        embedding_dimensions: int,
        embedding_batch_size: int,
    ) -> None:
        if embedding_dimensions < 1:
            raise ValueError("Embedding dimensions must be at least one")
        if embedding_batch_size < 1:
            raise ValueError("Embedding batch size must be at least one")
        self._embedding_provider = embedding_provider
        self._repository = repository
        self._embedding_dimensions = embedding_dimensions
        self._embedding_batch_size = embedding_batch_size

    def persist(
        self,
        processing_result: ContentProcessingResult,
        *,
        access_roles: Sequence[str] = ("user",),
    ) -> KnowledgePersistenceResult:
        started_at = monotonic()
        prepared = self.prepare(processing_result, access_roles=access_roles)
        return self.persist_prepared(prepared, started_at=started_at)

    def prepare(
        self,
        processing_result: ContentProcessingResult,
        *,
        access_roles: Sequence[str] = ("user",),
    ) -> PreparedKnowledge:
        started_at = monotonic()
        grouped_chunks = self._validate_and_group(processing_result)
        roles = self._normalise_roles(access_roles)
        logger.info(
            "Knowledge embedding preparation started",
            extra={
                "documents_received": len(grouped_chunks),
                "chunks_received": len(processing_result.chunks),
            },
        )

        prepared_documents: list[PreparedKnowledgeDocument] = []
        embeddings_generated = 0
        embedding_duration_ms = 0
        database_duration_ms = 0

        try:
            for source_url, source_chunks in grouped_chunks.items():
                ordered_chunks = sorted(source_chunks, key=lambda item: item.sequence)
                first = ordered_chunks[0]
                database_started_at = monotonic()
                try:
                    existing = self._repository.find_document_by_source_url(source_url)
                finally:
                    database_duration_ms += max(0, int((monotonic() - database_started_at) * 1_000))
                if existing and existing.content_hash == first.document_content_hash:
                    document = KnowledgeDocumentRecord(
                        id=existing.id,
                        source_url=source_url,
                        title=first.title,
                        content_hash=first.document_content_hash,
                        access_roles=roles,
                    )
                    prepared_documents.append(
                        PreparedKnowledgeDocument(
                            document=document,
                            chunks=(),
                            disposition=(
                                "unchanged"
                                if existing.title == first.title and existing.access_roles == roles
                                else "metadata"
                            ),
                            previous_chunk_count=len(ordered_chunks),
                        )
                    )
                    continue

                embedding_started_at = monotonic()
                try:
                    embeddings = self._embed([item.text for item in ordered_chunks])
                finally:
                    embedding_duration_ms += max(
                        0, int((monotonic() - embedding_started_at) * 1_000)
                    )
                embeddings_generated += len(embeddings)
                document_id = existing.id if existing else str(uuid5(NAMESPACE_URL, source_url))
                document = KnowledgeDocumentRecord(
                    id=document_id,
                    source_url=source_url,
                    title=first.title,
                    content_hash=first.document_content_hash,
                    access_roles=roles,
                )
                persisted_chunks = tuple(
                    PersistedKnowledgeChunk(
                        id=str(item.id),
                        document_id=document_id,
                        sequence=item.sequence,
                        text=item.text,
                        content_hash=item.content_hash,
                        embedding=tuple(embedding),
                        heading_path=item.heading_path,
                        access_roles=roles,
                    )
                    for item, embedding in zip(ordered_chunks, embeddings, strict=True)
                )
                prepared_documents.append(
                    PreparedKnowledgeDocument(document, persisted_chunks, "replace", 0)
                )
        except (EmbeddingGenerationError, InvalidKnowledgeInputError):
            self._log_failure(
                started_at,
                len(grouped_chunks),
                len(processing_result.chunks),
                embedding_duration_ms,
                database_duration_ms,
            )
            raise
        except Exception as exc:
            self._log_failure(
                started_at,
                len(grouped_chunks),
                len(processing_result.chunks),
                embedding_duration_ms,
                database_duration_ms,
            )
            raise KnowledgePersistenceError("Knowledge could not be prepared.") from exc

        return PreparedKnowledge(
            documents=tuple(prepared_documents),
            chunks_received=len(processing_result.chunks),
            embeddings_generated=embeddings_generated,
            embedding_duration_ms=embedding_duration_ms,
            database_duration_ms=database_duration_ms,
        )

    def persist_prepared(
        self,
        prepared: PreparedKnowledge,
        *,
        started_at: float | None = None,
    ) -> KnowledgePersistenceResult:
        operation_started_at = started_at if started_at is not None else monotonic()
        documents_created = 0
        documents_updated = 0
        documents_unchanged = 0
        chunks_created = 0
        chunks_updated = 0
        chunks_unchanged = 0
        chunks_removed = 0
        database_duration_ms = prepared.database_duration_ms
        try:
            for item in prepared.documents:
                if item.disposition == "unchanged":
                    documents_unchanged += 1
                    chunks_unchanged += item.previous_chunk_count
                    continue
                database_started_at = monotonic()
                try:
                    if item.disposition == "metadata":
                        write_result = self._repository.update_document_metadata(item.document)
                    else:
                        write_result = self._repository.replace_document(
                            item.document, list(item.chunks)
                        )
                finally:
                    database_duration_ms += max(0, int((monotonic() - database_started_at) * 1_000))
                if item.disposition == "metadata":
                    documents_updated += 1
                    chunks_updated += write_result.previous_chunk_count
                elif write_result.action == "created":
                    documents_created += 1
                    chunks_created += len(item.chunks)
                elif write_result.action == "updated":
                    documents_updated += 1
                    chunks_created += len(item.chunks)
                    chunks_removed += write_result.previous_chunk_count
                else:
                    documents_unchanged += 1
                    chunks_unchanged += len(item.chunks)
        except Exception as exc:
            self._log_failure(
                operation_started_at,
                len(prepared.documents),
                prepared.chunks_received,
                prepared.embedding_duration_ms,
                database_duration_ms,
            )
            raise KnowledgePersistenceError("Knowledge could not be persisted.") from exc

        outcome = KnowledgePersistenceResult(
            documents_received=len(prepared.documents),
            documents_created=documents_created,
            documents_updated=documents_updated,
            documents_unchanged=documents_unchanged,
            chunks_received=prepared.chunks_received,
            chunks_created=chunks_created,
            chunks_updated=chunks_updated,
            chunks_unchanged=chunks_unchanged,
            chunks_removed=chunks_removed,
            embeddings_generated=prepared.embeddings_generated,
            duration_ms=max(0, int((monotonic() - operation_started_at) * 1_000)),
            embedding_duration_ms=prepared.embedding_duration_ms,
            database_duration_ms=database_duration_ms,
        )
        logger.info(
            "Knowledge persistence completed",
            extra={
                "documents_received": outcome.documents_received,
                "documents_created": outcome.documents_created,
                "documents_updated": outcome.documents_updated,
                "documents_unchanged": outcome.documents_unchanged,
                "chunks_received": outcome.chunks_received,
                "chunks_created": outcome.chunks_created,
                "chunks_updated": outcome.chunks_updated,
                "chunks_unchanged": outcome.chunks_unchanged,
                "chunks_removed": outcome.chunks_removed,
                "embeddings_generated": outcome.embeddings_generated,
                "embedding_duration_ms": prepared.embedding_duration_ms,
                "database_duration_ms": database_duration_ms,
                "duration_ms": outcome.duration_ms,
            },
        )
        return outcome

    def _embed(self, texts: list[str]) -> list[list[float]]:
        embeddings: list[list[float]] = []
        for start in range(0, len(texts), self._embedding_batch_size):
            batch = texts[start : start + self._embedding_batch_size]
            try:
                batch_embeddings = self._embedding_provider.generate_embeddings(texts=batch)
            except Exception as exc:
                raise EmbeddingGenerationError(
                    "Knowledge embeddings could not be generated."
                ) from exc
            if len(batch_embeddings) != len(batch):
                raise EmbeddingGenerationError(
                    "The embedding provider returned the wrong number of embeddings."
                )
            for embedding in batch_embeddings:
                if len(embedding) != self._embedding_dimensions:
                    raise EmbeddingDimensionMismatchError(
                        "Embedding dimension mismatch: "
                        f"expected {self._embedding_dimensions}, received {len(embedding)}."
                    )
            embeddings.extend(batch_embeddings)
        return embeddings

    @staticmethod
    def _validate_and_group(
        processing_result: ContentProcessingResult,
    ) -> dict[str, list[KnowledgeChunk]]:
        if not processing_result.chunks:
            raise InvalidKnowledgeInputError("Processed knowledge must contain at least one chunk.")
        grouped: dict[str, list[KnowledgeChunk]] = defaultdict(list)
        for item in processing_result.chunks:
            if not item.source_url.strip():
                raise InvalidKnowledgeInputError("Knowledge chunk source URL must not be empty.")
            if not item.text.strip():
                raise InvalidKnowledgeInputError("Knowledge chunk text must not be empty.")
            if not item.content_hash.strip():
                raise InvalidKnowledgeInputError("Knowledge chunk content hash must not be empty.")
            if not item.document_content_hash.strip():
                raise InvalidKnowledgeInputError(
                    "Knowledge document content hash must not be empty."
                )
            grouped[item.source_url].append(item)

        for source_url, source_chunks in grouped.items():
            sequences = [item.sequence for item in source_chunks]
            if len(sequences) != len(set(sequences)):
                raise InvalidKnowledgeInputError(
                    f"Knowledge document contains a duplicate sequence for {source_url}."
                )
            content_hashes = [item.content_hash for item in source_chunks]
            if len(content_hashes) != len(set(content_hashes)):
                raise InvalidKnowledgeInputError(
                    f"Knowledge document contains a duplicate content hash for {source_url}."
                )
            document_hashes = {item.document_content_hash for item in source_chunks}
            if len(document_hashes) != 1:
                raise InvalidKnowledgeInputError(
                    f"Knowledge chunks disagree on the document content hash for {source_url}."
                )
        return dict(grouped)

    @staticmethod
    def _normalise_roles(access_roles: Sequence[str]) -> tuple[str, ...]:
        roles = tuple(dict.fromkeys(role.strip() for role in access_roles if role.strip()))
        if not roles:
            raise InvalidKnowledgeInputError("At least one access role is required.")
        return roles

    @staticmethod
    def _log_failure(
        started_at: float,
        documents: int,
        chunks: int,
        embedding_duration_ms: int,
        database_duration_ms: int,
    ) -> None:
        logger.warning(
            "Knowledge persistence failed",
            extra={
                "documents_received": documents,
                "chunks_received": chunks,
                "embedding_duration_ms": embedding_duration_ms,
                "database_duration_ms": database_duration_ms,
                "duration_ms": max(0, int((monotonic() - started_at) * 1_000)),
            },
        )
