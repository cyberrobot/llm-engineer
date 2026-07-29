import logging
from collections.abc import Sequence
from time import monotonic

from assistant.application.ports.content_extractor import ContentExtractor
from assistant.application.ports.text_chunker import TextChunker
from assistant.application.ports.text_cleaner import TextCleaner
from assistant.domain.content_processing_result import (
    ContentProcessingResult,
    ProcessingWarning,
)
from assistant.domain.knowledge_chunk import KnowledgeChunk
from assistant.domain.website_document import WebsiteDocument

logger = logging.getLogger(__name__)


class ContentProcessingError(RuntimeError):
    """Base error exposed by the content-processing application boundary."""


class NoProcessableContentError(ContentProcessingError):
    """Raised when none of the supplied raw documents can produce chunks."""

    def __init__(self, result: ContentProcessingResult) -> None:
        super().__init__("No supplied website document contained processable content.")
        self.result = result


class ContentProcessingService:
    """Orchestrate extraction, cleaning, and chunking without external side effects."""

    def __init__(
        self,
        extractor: ContentExtractor,
        cleaner: TextCleaner,
        chunker: TextChunker,
    ) -> None:
        self._extractor = extractor
        self._cleaner = cleaner
        self._chunker = chunker

    def process(self, documents: Sequence[WebsiteDocument]) -> ContentProcessingResult:
        started_at = monotonic()
        logger.info("Content processing started", extra={"documents_received": len(documents)})
        chunks: list[KnowledgeChunk] = []
        warnings: list[ProcessingWarning] = []
        documents_processed = 0
        failure_counts = {"extraction": 0, "cleaning": 0, "chunking": 0}

        for document in documents:
            try:
                extracted = self._extractor.extract(document)
            except Exception:
                failure_counts["extraction"] += 1
                self._warn(
                    warnings,
                    document.url,
                    "extraction_failed",
                    "The page could not be parsed and was skipped.",
                )
                continue
            if extracted is None:
                self._warn(
                    warnings,
                    document.url,
                    "no_meaningful_content",
                    "No meaningful page content was found.",
                )
                continue

            try:
                clean = self._cleaner.clean(extracted)
            except Exception:
                failure_counts["cleaning"] += 1
                self._warn(
                    warnings,
                    document.url,
                    "cleaning_failed",
                    "The extracted page could not be normalised and was skipped.",
                )
                continue
            if clean is None:
                self._warn(
                    warnings,
                    document.url,
                    "content_below_minimum",
                    "Too little meaningful content remained after normalisation.",
                )
                continue

            try:
                page_chunks = self._chunker.chunk(clean)
            except Exception:
                failure_counts["chunking"] += 1
                self._warn(
                    warnings,
                    document.url,
                    "chunking_failed",
                    "The cleaned page could not be chunked and was skipped.",
                )
                continue
            if not page_chunks:
                self._warn(
                    warnings,
                    document.url,
                    "no_chunks_created",
                    "The cleaned page did not produce any non-empty chunks.",
                )
                continue
            chunks.extend(page_chunks)
            documents_processed += 1

        result = ContentProcessingResult(
            documents_received=len(documents),
            documents_processed=documents_processed,
            documents_skipped=len(documents) - documents_processed,
            chunks_created=len(chunks),
            chunks=chunks,
            warnings=warnings,
            duration_ms=max(0, int((monotonic() - started_at) * 1000)),
        )
        self._log_result(result, failure_counts)
        if not chunks:
            raise NoProcessableContentError(result)
        return result

    @staticmethod
    def _warn(warnings: list[ProcessingWarning], source_url: str, code: str, message: str) -> None:
        warnings.append(ProcessingWarning(source_url=source_url, code=code, message=message))
        logger.warning("Website document skipped", extra={"source_url": source_url, "code": code})

    @staticmethod
    def _log_result(result: ContentProcessingResult, failure_counts: dict[str, int]) -> None:
        logger.info(
            "Content processing completed",
            extra={
                "documents_received": result.documents_received,
                "documents_processed": result.documents_processed,
                "documents_skipped": result.documents_skipped,
                "chunks_created": result.chunks_created,
                "duration_ms": result.duration_ms,
                "extraction_failures": failure_counts["extraction"],
                "cleaning_failures": failure_counts["cleaning"],
                "chunking_failures": failure_counts["chunking"],
            },
        )
