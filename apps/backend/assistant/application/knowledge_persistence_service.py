import hashlib
import json
import logging
import re
from collections import defaultdict
from collections.abc import Sequence
from time import monotonic
from uuid import NAMESPACE_URL, UUID, uuid5

import psycopg

from assistant.application.ports.embedding_provider import EmbeddingProvider
from assistant.domain.assistant import REDMOOR_ASSISTANT_ID
from assistant.domain.content_processing_result import ContentProcessingResult
from assistant.domain.knowledge_chunk import KnowledgeChunk
from assistant.domain.knowledge_persistence import (
    CommittedIngestionResult,
    KnowledgeDocumentRecord,
    KnowledgePersistenceRepository,
    KnowledgePersistenceResult,
    KnowledgePersistenceWriteConflict,
    PersistedKnowledgeChunk,
    PersistenceMode,
    PersistIngestionResult,
    PreparedKnowledge,
    PreparedKnowledgeDocument,
)
from core.metrics import IngestionOperationalMetrics, ingestion_operational_metrics

logger = logging.getLogger(__name__)


class KnowledgePersistenceError(RuntimeError):
    """Base error exposed by the knowledge-persistence application boundary."""

    code = "ingestion_persistence_failed"


class IngestionPersistenceConflictError(KnowledgePersistenceError):
    code = "ingestion_persistence_conflict"


class IngestionPersistenceTransientError(KnowledgePersistenceError):
    code = "ingestion_persistence_transient_error"


class IngestionPersistenceConsistencyError(KnowledgePersistenceError):
    code = "ingestion_persistence_inconsistent_state"


class InvalidKnowledgeInputError(KnowledgePersistenceError):
    """Raised before side effects when processed knowledge violates its contract."""

    code = "invalid_ingestion_persistence_input"


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
        assistant_id: UUID,
        embedding_dimensions: int,
        embedding_batch_size: int,
        metrics: IngestionOperationalMetrics = ingestion_operational_metrics,
    ) -> None:
        if embedding_dimensions < 1:
            raise ValueError("Embedding dimensions must be at least one")
        if embedding_batch_size < 1:
            raise ValueError("Embedding batch size must be at least one")
        self._embedding_provider = embedding_provider
        self._repository = repository
        self._assistant_id = assistant_id
        self._embedding_dimensions = embedding_dimensions
        self._embedding_batch_size = embedding_batch_size
        self._metrics = metrics

    def persist(
        self,
        processing_result: ContentProcessingResult,
        *,
        access_roles: Sequence[str] = ("user",),
        mode: PersistenceMode = PersistenceMode.new,
    ) -> KnowledgePersistenceResult:
        started_at = monotonic()
        prepared = self.prepare(
            processing_result,
            access_roles=access_roles,
            force_replace=mode is PersistenceMode.reindex,
        )
        return self.persist_prepared(prepared, started_at=started_at)

    def prepare(
        self,
        processing_result: ContentProcessingResult,
        *,
        access_roles: Sequence[str] = ("user",),
        force_replace: bool = False,
    ) -> PreparedKnowledge:
        started_at = monotonic()
        grouped_chunks = self._validate_and_group(processing_result)
        roles = self._normalise_roles(access_roles)
        logger.info(
            "Knowledge embedding preparation started",
            extra={
                "assistant_id": str(self._assistant_id),
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
                    existing = self._repository.find_document_by_source_url(
                        source_url, assistant_id=self._assistant_id
                    )
                finally:
                    database_duration_ms += max(0, int((monotonic() - database_started_at) * 1_000))
                if (
                    existing
                    and existing.content_hash == first.document_content_hash
                    and not force_replace
                ):
                    document = KnowledgeDocumentRecord(
                        id=existing.id,
                        assistant_id=self._assistant_id,
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
                            expected_previous_content_hash=existing.content_hash,
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
                document_id = existing.id if existing else self._document_id(source_url)
                document = KnowledgeDocumentRecord(
                    id=document_id,
                    assistant_id=self._assistant_id,
                    source_url=source_url,
                    title=first.title,
                    content_hash=first.document_content_hash,
                    access_roles=roles,
                )
                persisted_chunks = tuple(
                    PersistedKnowledgeChunk(
                        id=self._chunk_id(str(item.id)),
                        assistant_id=self._assistant_id,
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
                    PreparedKnowledgeDocument(
                        document,
                        persisted_chunks,
                        "replace",
                        0,
                        existing.content_hash if existing else None,
                    )
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
        command: PersistIngestionResult | None = None,
    ) -> KnowledgePersistenceResult:
        operation_started_at = started_at if started_at is not None else monotonic()
        try:
            self._validate_prepared(prepared)
            if command is not None:
                self._validate_command(command, prepared)
        except InvalidKnowledgeInputError:
            logger.warning(
                "ingestion_persistence_validation_failed",
                extra=self._log_context(command, prepared),
            )
            raise
        logger.info(
            "ingestion_persistence_started",
            extra=self._log_context(command, prepared),
        )
        documents_created = 0
        documents_updated = 0
        documents_unchanged = 0
        chunks_created = 0
        chunks_updated = 0
        chunks_unchanged = 0
        chunks_removed = 0
        activated_documents: list[str] = []
        superseded_documents: list[str] = []
        database_duration_ms = prepared.database_duration_ms
        try:
            database_started_at = monotonic()
            logger.info(
                "ingestion_persistence_transaction_started",
                extra=self._log_context(command, prepared),
            )
            with self._repository.transaction() as transaction:
                if command is not None:
                    transaction.lock_ingestion_job(command.ingestion_job_id, command.document_id)
                    committed = transaction.find_committed_result(command.ingestion_job_id)
                    if committed is not None:
                        return self._resolve_committed_result(committed, command, prepared)
                for item in prepared.documents:
                    if item.disposition == "unchanged":
                        documents_unchanged += 1
                        chunks_unchanged += item.previous_chunk_count
                        continue
                    if item.disposition == "metadata":
                        write_result = transaction.update_document_metadata(item.document)
                    else:
                        write_result = transaction.replace_document(
                            item.document,
                            list(item.chunks),
                            ingestion_job_id=(command.ingestion_job_id if command else None),
                            expected_previous_content_hash=item.expected_previous_content_hash,
                            force_replace=(
                                command is not None and command.mode is PersistenceMode.reindex
                            ),
                        )
                    if item.disposition == "metadata":
                        documents_updated += 1
                        chunks_updated += write_result.previous_chunk_count
                    elif write_result.action == "created":
                        documents_created += 1
                        chunks_created += len(item.chunks)
                        activated_documents.append(write_result.document_id)
                    elif write_result.action == "updated":
                        documents_updated += 1
                        chunks_created += len(item.chunks)
                        chunks_removed += write_result.previous_chunk_count
                        activated_documents.append(write_result.document_id)
                        superseded_documents.append(write_result.document_id)
                    else:
                        documents_unchanged += 1
                        chunks_unchanged += len(item.chunks)

                database_duration_ms += max(0, int((monotonic() - database_started_at) * 1_000))
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
                if command is not None:
                    transaction.record_committed_result(command, outcome)
        except KnowledgePersistenceError as exc:
            self._metric("persistence_rolled_back")
            if isinstance(
                exc,
                (IngestionPersistenceConflictError, IngestionPersistenceConsistencyError),
            ):
                logger.warning(
                    "ingestion_persistence_conflict",
                    extra=self._log_context(command, prepared),
                )
            logger.warning(
                "ingestion_persistence_rolled_back",
                extra=self._log_context(command, prepared),
            )
            raise
        except Exception as exc:
            self._metric("persistence_rolled_back")
            self._log_failure(
                operation_started_at,
                len(prepared.documents),
                prepared.chunks_received,
                prepared.embedding_duration_ms,
                database_duration_ms,
            )
            logger.warning(
                "ingestion_persistence_rolled_back",
                extra=self._log_context(command, prepared),
            )
            mapped = self._map_persistence_error(exc)
            if isinstance(
                mapped,
                (IngestionPersistenceConflictError, IngestionPersistenceConsistencyError),
            ):
                logger.warning(
                    "ingestion_persistence_conflict",
                    extra=self._log_context(command, prepared),
                )
            raise mapped from exc

        for document_id in superseded_documents:
            logger.info(
                "ingestion_representation_superseded",
                extra={**self._log_context(command, prepared), "document_id": document_id},
            )
        for document_id in activated_documents:
            logger.info(
                "ingestion_representation_activated",
                extra={**self._log_context(command, prepared), "document_id": document_id},
            )

        logger.info(
            "ingestion_persistence_committed",
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

    def _metric(self, method: str, *args: object) -> None:
        try:
            getattr(self._metrics, method)(*args)
        except Exception:
            logger.warning("ingestion_telemetry_export_failed", extra={"reason": method})

    def create_command(
        self,
        prepared: PreparedKnowledge,
        *,
        ingestion_job_id: UUID,
        document_id: str,
        mode: PersistenceMode = PersistenceMode.new,
        source_fingerprint: str | None = None,
    ) -> PersistIngestionResult:
        self._validate_prepared(prepared)
        if not document_id.strip():
            raise InvalidKnowledgeInputError("Document identity must not be empty.")
        if (
            source_fingerprint is not None
            and re.fullmatch(r"[0-9a-f]{64}", source_fingerprint) is None
        ):
            raise InvalidKnowledgeInputError("Source fingerprint must be a SHA-256 digest.")
        payload = {
            "document_id": document_id,
            "mode": mode.value,
            "source_fingerprint": source_fingerprint,
            "documents": [
                {
                    "id": item.document.id,
                    "assistant_id": str(item.document.assistant_id),
                    "source_url": item.document.source_url,
                    "title": item.document.title,
                    "content_hash": item.document.content_hash,
                    "access_roles": item.document.access_roles,
                }
                for item in prepared.documents
            ],
        }
        command_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return PersistIngestionResult(
            ingestion_job_id,
            document_id,
            prepared,
            mode,
            command_hash,
            source_fingerprint,
        )

    @staticmethod
    def _validate_command(command: PersistIngestionResult, prepared: PreparedKnowledge) -> None:
        if command.prepared != prepared:
            raise InvalidKnowledgeInputError("Persistence command data does not match its payload.")
        if (
            not command.document_id.strip()
            or re.fullmatch(r"[0-9a-f]{64}", command.command_hash) is None
        ):
            raise InvalidKnowledgeInputError("Persistence command identity is invalid.")

    def _validate_prepared(self, prepared: PreparedKnowledge) -> None:
        if not prepared.documents:
            raise InvalidKnowledgeInputError(
                "Prepared knowledge must contain at least one document."
            )
        chunk_ids: set[str] = set()
        for item in prepared.documents:
            if not item.document.id.strip() or not item.document.source_url.strip():
                raise InvalidKnowledgeInputError("Prepared document identity is invalid.")
            if item.disposition == "replace" and not item.chunks:
                raise InvalidKnowledgeInputError("Replacement must contain at least one chunk.")
            for chunk in item.chunks:
                if chunk.id in chunk_ids:
                    raise InvalidKnowledgeInputError("Prepared chunk identifiers must be unique.")
                chunk_ids.add(chunk.id)
                if chunk.document_id != item.document.id or not chunk.text.strip():
                    raise InvalidKnowledgeInputError("Prepared chunk association is invalid.")
                if (
                    item.document.assistant_id != self._assistant_id
                    or chunk.assistant_id != item.document.assistant_id
                ):
                    raise InvalidKnowledgeInputError("Prepared assistant association is invalid.")
                if len(chunk.embedding) != self._embedding_dimensions:
                    raise InvalidKnowledgeInputError("Prepared embedding dimensions are invalid.")

    @staticmethod
    def _resolve_committed_result(
        committed: CommittedIngestionResult,
        command: PersistIngestionResult,
        prepared: PreparedKnowledge,
    ) -> KnowledgePersistenceResult:
        if (
            committed.document_id != command.document_id
            or committed.command_hash != command.command_hash
        ):
            raise IngestionPersistenceConsistencyError(
                "The ingestion job already committed a different representation."
            )
        logger.info(
            "ingestion_persistence_retry_detected_existing_commit",
            extra=KnowledgePersistenceService._log_context(command, prepared),
        )
        return committed.result

    @staticmethod
    def _map_persistence_error(error: Exception) -> KnowledgePersistenceError:
        if isinstance(error, (psycopg.OperationalError, psycopg.errors.DeadlockDetected)):
            return IngestionPersistenceTransientError(
                "Knowledge persistence is temporarily unavailable."
            )
        if isinstance(error, psycopg.IntegrityError):
            return IngestionPersistenceConflictError(
                "Knowledge persistence conflicted with existing data."
            )
        if isinstance(error, KnowledgePersistenceWriteConflict):
            return IngestionPersistenceConflictError(
                "The indexed document changed while its replacement was being persisted."
            )
        return KnowledgePersistenceError("Knowledge could not be persisted.")

    @staticmethod
    def _log_context(
        command: PersistIngestionResult | None, prepared: PreparedKnowledge
    ) -> dict[str, object]:
        return {
            "ingestion_job_id": str(command.ingestion_job_id) if command else None,
            "assistant_id": (
                str(prepared.documents[0].document.assistant_id) if prepared.documents else None
            ),
            "document_id": command.document_id if command else None,
            "persistence_mode": command.mode.value if command else None,
            "chunk_count": prepared.chunks_received,
            "embedding_count": prepared.embeddings_generated,
        }

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

    def _document_id(self, source_url: str) -> str:
        identity = (
            source_url
            if self._assistant_id == REDMOOR_ASSISTANT_ID
            else f"{self._assistant_id}\0{source_url}"
        )
        return str(uuid5(NAMESPACE_URL, identity))

    def _chunk_id(self, chunk_id: str) -> str:
        if self._assistant_id == REDMOOR_ASSISTANT_ID:
            return chunk_id
        return str(uuid5(NAMESPACE_URL, f"{self._assistant_id}\0{chunk_id}"))

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
