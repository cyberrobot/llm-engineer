import hashlib
import json
from dataclasses import dataclass

from assistant.application.ports.knowledge_source_repository import (
    KnowledgeSourceConflict,
    KnowledgeSourceRepository,
)
from assistant.domain.document_ingestion_job import DocumentIngestionJob
from assistant.domain.knowledge_source import KnowledgeSource


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
    def __init__(self, repository: KnowledgeSourceRepository, assistant_repository) -> None:
        self.repository = repository
        self.assistants = assistant_repository

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
            previous = self.repository.find_creation(key)
            if previous:
                if previous[1] != request_hash:
                    raise IdempotencyConflict("Idempotency key conflicts with another request.")
                prior = previous[0]
                return KnowledgeSourceView(
                    prior, self.repository.latest_job(prior.document_id)
                ), True
        job = DocumentIngestionJob.create(source.document_id, idempotency_key=key)
        try:
            with self.repository.transaction() as transaction:
                created, queued = transaction.create(source, job, request_hash, job.idempotency_key)
            return KnowledgeSourceView(created, queued), False
        except KnowledgeSourceConflict as exc:
            if key:
                previous = self.repository.find_creation(key)
                if previous and previous[1] == request_hash:
                    prior = previous[0]
                    return KnowledgeSourceView(
                        prior, self.repository.latest_job(prior.document_id)
                    ), True
            # Resolve concurrent URL winners without exposing an integrity error.
            items, _ = self.repository.list(assistant_id, limit=100, offset=0)
            winner = next((item for item in items if source.url and item.url == source.url), None)
            if winner is not None:
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
        return KnowledgeSourceView(source, self.repository.latest_job(source.document_id))

    def reingest(self, assistant_id, source_id, *, idempotency_key=None):
        view = self.get(assistant_id, source_id)
        active = self.repository.active_job(view.source.document_id)
        if active:
            return KnowledgeSourceView(view.source, active), True
        job = DocumentIngestionJob.create(
            view.source.document_id,
            idempotency_key=idempotency_key.strip() if idempotency_key else None,
        )
        return KnowledgeSourceView(view.source, self.repository.create_job(job)), False

    def delete(self, assistant_id, source_id):
        self._assistant(assistant_id)
        try:
            with self.repository.transaction() as transaction:
                deleted = transaction.delete(assistant_id, source_id)
        except KnowledgeSourceConflict as exc:
            raise ActiveIngestionConflict from exc
        if not deleted:
            raise KnowledgeSourceNotFound

    def _assistant(self, assistant_id):
        try:
            return self.assistants.get_by_id(assistant_id)
        except LookupError as exc:
            raise KnowledgeSourceNotFound from exc
