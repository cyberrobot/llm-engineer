from dataclasses import dataclass
from uuid import UUID

from assistant.application.content_processing_service import ContentProcessingService
from assistant.application.ingestion_pipeline import REQUIRED_STEP_ORDER, IngestionPipelineContext
from assistant.application.knowledge_persistence_service import KnowledgePersistenceService
from assistant.application.ports.website_loader import WebsiteLoader
from assistant.domain.document_ingestion_job import IngestionStep
from assistant.infrastructure.repositories.document_ingestion_job import (
    DocumentIngestionJobRepository,
)


@dataclass(frozen=True)
class WebsiteIngestionContextFactory:
    repository: DocumentIngestionJobRepository
    loader: WebsiteLoader
    processor: ContentProcessingService
    persistence: KnowledgePersistenceService

    def __call__(
        self,
        job_id: UUID,
        document_id: str,
        last_completed_step: IngestionStep | None,
    ) -> IngestionPipelineContext:
        source = self.repository.get_document_source(document_id)
        if source is None:
            if last_completed_step is None:
                return IngestionPipelineContext(job_id, document_id)
            raise LookupError("Document has no supported website source.")
        context = IngestionPipelineContext(
            job_id,
            document_id,
            metadata={"source_url": source.source_url, "access_roles": source.access_roles},
        )
        if last_completed_step is None:
            return context
        checkpoint_index = REQUIRED_STEP_ORDER.index(last_completed_step)
        if checkpoint_index >= REQUIRED_STEP_ORDER.index(IngestionStep.parse):
            context.parsed_document = self.loader.load(source.source_url)
        if checkpoint_index >= REQUIRED_STEP_ORDER.index(IngestionStep.chunk):
            if context.parsed_document is None:
                raise RuntimeError("Parsed document reconstruction failed.")
            context.chunks = self.processor.process(context.parsed_document)
        if checkpoint_index >= REQUIRED_STEP_ORDER.index(IngestionStep.embed):
            if context.chunks is None:
                raise RuntimeError("Chunk reconstruction failed.")
            context.embeddings = self.persistence.prepare(
                context.chunks, access_roles=source.access_roles
            )
        return context
