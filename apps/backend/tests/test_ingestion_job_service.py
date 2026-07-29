from uuid import uuid4

import pytest

from assistant.application.ingestion_job_service import (
    DocumentIngestionJobService,
    DocumentNotFound,
    IdempotencyKeyConflict,
    InvalidIdempotencyKey,
)
from assistant.infrastructure.repositories.document_ingestion_job import (
    InMemoryDocumentIngestionJobRepository,
)


def service_for(document_id: str):
    repository = InMemoryDocumentIngestionJobRepository(document_ids={document_id})
    return DocumentIngestionJobService(repository), repository


def test_service_creates_retrieves_and_lists_a_queued_job():
    document_id = str(uuid4())
    service, _repository = service_for(document_id)

    created = service.create(document_id)
    loaded = service.get(created.id)
    page = service.list(limit=20, offset=0, document_id=document_id)

    assert loaded == created
    assert page.items == [created]
    assert page.total == 1


def test_service_rejects_unknown_document_without_side_effects():
    service, repository = service_for(str(uuid4()))

    with pytest.raises(DocumentNotFound):
        service.create(str(uuid4()))

    assert repository.list(limit=10, offset=0).total == 0


def test_idempotency_replay_returns_same_job_and_conflicting_document_is_rejected():
    first_document = str(uuid4())
    second_document = str(uuid4())
    repository = InMemoryDocumentIngestionJobRepository(
        document_ids={first_document, second_document}
    )
    service = DocumentIngestionJobService(repository)

    first = service.create(first_document, idempotency_key=" Case-Sensitive-Key ")
    repeated = service.create(first_document, idempotency_key="Case-Sensitive-Key")

    assert repeated.id == first.id
    assert repository.list(limit=10, offset=0).total == 1
    with pytest.raises(IdempotencyKeyConflict):
        service.create(second_document, idempotency_key="Case-Sensitive-Key")
    assert repository.list(limit=10, offset=0).total == 1


@pytest.mark.parametrize("key", ["", "   ", "x" * 256])
def test_service_rejects_invalid_idempotency_keys(key):
    document_id = str(uuid4())
    service, _repository = service_for(document_id)
    with pytest.raises(InvalidIdempotencyKey):
        service.create(document_id, idempotency_key=key)
