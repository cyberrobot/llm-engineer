import logging
from dataclasses import dataclass

from assistant.application.content_processing_service import ContentProcessingService
from assistant.application.ingestion_pipeline import (
    IngestionPipelineContext,
    IngestionStepResult,
)
from assistant.application.knowledge_persistence_service import KnowledgePersistenceService
from assistant.application.ports.website_loader import WebsiteLoader
from assistant.domain.document_ingestion_job import IngestionStep
from assistant.domain.knowledge_persistence import PersistenceMode, PreparedKnowledge

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ParseIngestionStep:
    loader: WebsiteLoader
    step_id = IngestionStep.parse

    def execute(self, context: IngestionPipelineContext) -> IngestionStepResult:
        source_url = context.metadata.get("source_url")
        if not isinstance(source_url, str) or not source_url.strip():
            return IngestionStepResult.failure(
                "ingestion_source_unavailable", "The ingestion source is unavailable."
            )
        try:
            context.parsed_document = self.loader.load(source_url)
        except Exception as exc:
            logger.exception(
                "Document parsing failed",
                extra={"job_id": str(context.job_id), "document_id": context.document_id},
            )
            return IngestionStepResult.failure(
                "document_parse_failed", "The source document could not be parsed.", cause=exc
            )
        return IngestionStepResult.success()


@dataclass(frozen=True)
class ChunkIngestionStep:
    processor: ContentProcessingService
    step_id = IngestionStep.chunk

    def execute(self, context: IngestionPipelineContext) -> IngestionStepResult:
        if context.parsed_document is None:
            return IngestionStepResult.failure(
                "missing_parsed_document", "Parsed document data is unavailable."
            )
        try:
            context.chunks = self.processor.process(context.parsed_document)
        except Exception as exc:
            logger.exception(
                "Document chunking failed",
                extra={"job_id": str(context.job_id), "document_id": context.document_id},
            )
            return IngestionStepResult.failure(
                "document_chunking_failed", "The document could not be chunked.", cause=exc
            )
        return IngestionStepResult.success()


@dataclass(frozen=True)
class EmbedIngestionStep:
    persistence: KnowledgePersistenceService
    step_id = IngestionStep.embed

    def execute(self, context: IngestionPipelineContext) -> IngestionStepResult:
        if context.chunks is None:
            return IngestionStepResult.failure(
                "missing_ingestion_chunks", "Document chunks are unavailable."
            )
        access_roles = context.metadata.get("access_roles", ("user",))
        if not isinstance(access_roles, (tuple, list)) or not all(
            isinstance(role, str) for role in access_roles
        ):
            return IngestionStepResult.failure(
                "invalid_ingestion_metadata", "Document access roles are invalid."
            )
        try:
            mode_value = context.metadata.get("persistence_mode", PersistenceMode.new.value)
            try:
                mode = PersistenceMode(mode_value)
            except (TypeError, ValueError) as exc:
                return IngestionStepResult.failure(
                    "invalid_ingestion_persistence_input",
                    "The ingestion persistence mode is invalid.",
                    cause=exc,
                )
            context.embeddings = self.persistence.prepare(
                context.chunks,
                access_roles=tuple(access_roles),
                force_replace=mode is PersistenceMode.reindex,
            )
        except Exception as exc:
            logger.exception(
                "Document embedding failed",
                extra={"job_id": str(context.job_id), "document_id": context.document_id},
            )
            return IngestionStepResult.failure(
                "document_embedding_failed",
                "Document embeddings could not be generated.",
                cause=exc,
            )
        return IngestionStepResult.success()


@dataclass(frozen=True)
class PersistIngestionStep:
    persistence: KnowledgePersistenceService
    step_id = IngestionStep.persist

    def execute(self, context: IngestionPipelineContext) -> IngestionStepResult:
        if not isinstance(context.embeddings, PreparedKnowledge):
            return IngestionStepResult.failure(
                "missing_ingestion_embeddings", "Prepared document embeddings are unavailable."
            )
        try:
            mode_value = context.metadata.get("persistence_mode", PersistenceMode.new.value)
            try:
                mode = PersistenceMode(mode_value)
            except (TypeError, ValueError) as exc:
                return IngestionStepResult.failure(
                    "invalid_ingestion_persistence_input",
                    "The ingestion persistence mode is invalid.",
                    cause=exc,
                )
            fingerprint = context.metadata.get("source_fingerprint")
            if fingerprint is not None and not isinstance(fingerprint, str):
                return IngestionStepResult.failure(
                    "invalid_ingestion_persistence_input",
                    "The ingestion source fingerprint is invalid.",
                )
            command = self.persistence.create_command(
                context.embeddings,
                ingestion_job_id=context.job_id,
                document_id=context.document_id,
                mode=mode,
                source_fingerprint=fingerprint,
            )
            context.metadata["persistence_result"] = self.persistence.persist_prepared(
                context.embeddings, command=command
            )
        except Exception as exc:
            logger.exception(
                "Document persistence failed",
                extra={"job_id": str(context.job_id), "document_id": context.document_id},
            )
            return IngestionStepResult.failure(
                "document_persistence_failed",
                "Document knowledge could not be persisted.",
                cause=exc,
            )
        return IngestionStepResult.success()
