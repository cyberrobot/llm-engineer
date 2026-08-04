import hashlib
import json
import logging
from dataclasses import dataclass

from assistant.application.ports.knowledge_source_repository import (
    KnowledgeSourceConflict,
    KnowledgeSourceRepository,
)
from assistant.domain.document_ingestion_job import DocumentIngestionJob
from assistant.domain.knowledge_source import KnowledgeSource
from core.metrics import KnowledgeSourceMetrics, knowledge_source_metrics

logger = logging.getLogger(__name__)


class KnowledgeSourceNotFound(LookupError):
    pass


class ActiveIngestionConflict(RuntimeError):
    pass


class IdempotencyConflict(RuntimeError):
    pass


@dataclass(frozen=True)
class KnowledgeSourceView:
    source: KnowledgeSource
    latest_job: DocumentIngestionJob | None


class KnowledgeSourceService:
    def __init__(
        self,
        repository: KnowledgeSourceRepository,
        assistant_repository,
        metrics: KnowledgeSourceMetrics = knowledge_source_metrics,
    ) -> None:
        self.repository = repository
        self.assistants = assistant_repository
        self.metrics = metrics

    def create(
        self, assistant_id, *, source_type, name, direct_text=None, url=None, idempotency_key=None
    ):
        self._assistant(assistant_id)
        key = idempotency_key.strip() if idempotency_key else None
        source = KnowledgeSource.create(
            assistant_id=assistant_id,
            source_type=source_type,
            name=name,
            direct_text=direct_text,
            url=url,
        )
        request_hash = hashlib.sha256(
            json.dumps(
                {
                    "assistant_id": str(assistant_id),
                    "type": source_type.value,
                    "name": source.name,
                    "direct_text": direct_text,
                    "url": source.url,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        if key:
            previous = self.repository.find_creation(assistant_id, key)
            if previous:
                if previous[1] != request_hash:
                    raise IdempotencyConflict("Idempotency key conflicts with another request.")
                prior = previous[0]
                self.metrics.replayed.inc()
                logger.info("Knowledge source creation replayed", extra=_log_fields(prior))
                return KnowledgeSourceView(
                    prior, self.repository.latest_job(prior.document_id)
                ), True
        # Knowledge-source receipts own assistant-scoped replay identity. Keeping the
        # key off the shared job table avoids its legacy global job-key constraint.
        job = DocumentIngestionJob.create(source.document_id)
        try:
            with self.repository.transaction() as transaction:
                created, queued = transaction.create(source, job, request_hash, key)
            self.metrics.created.inc()
            logger.info("Knowledge source created", extra=_log_fields(created))
            return KnowledgeSourceView(created, queued), False
        except KnowledgeSourceConflict as exc:
            if key:
                previous = self.repository.find_creation(assistant_id, key)
                if previous and previous[1] == request_hash:
                    prior = previous[0]
                    self.metrics.replayed.inc()
                    logger.info("Knowledge source creation replayed", extra=_log_fields(prior))
                    return KnowledgeSourceView(
                        prior, self.repository.latest_job(prior.document_id)
                    ), True
            winner = self.repository.find_by_url(assistant_id, source.url) if source.url else None
            if winner is not None:
                self.metrics.duplicate_urls.inc()
                logger.info("Duplicate knowledge source URL detected", extra=_log_fields(winner))
                return KnowledgeSourceView(
                    winner, self.repository.latest_job(winner.document_id)
                ), True
            raise IdempotencyConflict("Idempotency key conflicts with another request.") from exc

    def list(self, assistant_id, *, limit, offset):
        self._assistant(assistant_id)
        sources, total = self.repository.list(assistant_id, limit=limit, offset=offset)
        return [
            KnowledgeSourceView(source, self.repository.latest_job(source.document_id))
            for source in sources
        ], total

    def get(self, assistant_id, source_id):
        self._assistant(assistant_id)
        source = self.repository.get(assistant_id, source_id)
        if source is None:
            raise KnowledgeSourceNotFound
        return KnowledgeSourceView(source, self.repository.latest_job(source.document_id))

    def update(self, assistant_id, source_id, state):
        self._assistant(assistant_id)
        with self.repository.transaction() as transaction:
            source = transaction.update_retrieval_state(assistant_id, source_id, state)
        if source is None:
            raise KnowledgeSourceNotFound
        metric = (
            self.metrics.retrieval_enabled
            if state.value == "enabled"
            else self.metrics.retrieval_disabled
        )
        metric.inc()
        logger.info("Knowledge source retrieval state updated", extra=_log_fields(source))
        return KnowledgeSourceView(source, self.repository.latest_job(source.document_id))

    def reingest(self, assistant_id, source_id, *, idempotency_key=None):
        self._assistant(assistant_id)
        current = self.repository.get(assistant_id, source_id)
        if current is None:
            raise KnowledgeSourceNotFound
        key = idempotency_key.strip() if idempotency_key else None
        request_hash = hashlib.sha256(
            json.dumps(
                {
                    "assistant_id": str(assistant_id),
                    "source_id": str(source_id),
                    "action": "reingest",
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        job = DocumentIngestionJob.create(current.document_id)
        try:
            with self.repository.transaction() as transaction:
                source, selected, reused = transaction.reingest(
                    assistant_id, source_id, job, request_hash, key
                )
        except LookupError as exc:
            raise KnowledgeSourceNotFound from exc
        except KnowledgeSourceConflict as exc:
            raise IdempotencyConflict("Idempotency key conflicts with another request.") from exc
        if reused:
            self.metrics.replayed.inc()
            logger.info("Knowledge source re-ingestion replayed", extra=_log_fields(source))
        else:
            self.metrics.reingested.inc()
            logger.info("Knowledge source re-ingestion queued", extra=_log_fields(source))
        return KnowledgeSourceView(source, selected), reused

    def delete(self, assistant_id, source_id):
        self._assistant(assistant_id)
        try:
            with self.repository.transaction() as transaction:
                deleted = transaction.delete(assistant_id, source_id)
        except KnowledgeSourceConflict as exc:
            logger.info(
                "Knowledge source deletion rejected for active ingestion",
                extra={"assistant_id": str(assistant_id), "source_id": str(source_id)},
            )
            raise ActiveIngestionConflict from exc
        if not deleted:
            raise KnowledgeSourceNotFound
        self.metrics.deleted.inc()
        logger.info(
            "Knowledge source deleted",
            extra={"assistant_id": str(assistant_id), "source_id": str(source_id)},
        )

    def _assistant(self, assistant_id):
        try:
            return self.assistants.get_by_id(assistant_id)
        except LookupError as exc:
            raise KnowledgeSourceNotFound from exc


def _log_fields(source: KnowledgeSource) -> dict[str, str]:
    return {
        "assistant_id": str(source.assistant_id),
        "source_id": str(source.id),
        "document_id": source.document_id,
        "source_type": source.source_type.value,
    }
