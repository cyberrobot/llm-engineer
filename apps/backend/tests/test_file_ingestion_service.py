from dataclasses import replace
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from assistant.application.file_ingestion import (
    FileIngestionRequest,
    FileIngestionService,
    IdempotentFileRequestConflict,
)
from assistant.domain.file_fingerprint import ContentStatus, FileFingerprint
from assistant.domain.ingestion_status import IngestionStatus
from assistant.infrastructure.repositories.file_ingestion import InMemoryFileIngestionRepository

NOW = datetime(2026, 7, 30, 10, 0, tzinfo=timezone.utc)


def request(
    content: bytes = b"%PDF-1.7 policy",
    *,
    filename: str = "policy.pdf",
    roles: tuple[str, ...] = ("user",),
    document_id: str | None = None,
    force_reindex: bool = False,
    idempotency_key: str | None = None,
    mime_type: str = "application/pdf",
) -> FileIngestionRequest:
    import hashlib

    return FileIngestionRequest(
        document_id=document_id,
        doc_type="policy",
        access_roles=roles,
        upload_path=f"/private/uploads/{uuid4()}.pdf",
        original_filename=filename,
        mime_type=mime_type,
        fingerprint=FileFingerprint("sha256", hashlib.sha256(content).hexdigest(), len(content)),
        checksum_calculated_at=NOW,
        force_reindex=force_reindex,
        idempotency_key=idempotency_key,
    )


def test_new_and_identical_content_create_one_document_and_one_job():
    repository = InMemoryFileIngestionRepository()
    service = FileIngestionService(repository)

    created = service.submit(request(filename="first.pdf"))
    duplicate = service.submit(request(filename="renamed.pdf"))

    assert created.content_status is ContentStatus.new_content
    assert created.ingestion_required
    assert not created.deduplicated
    assert duplicate.content_status is ContentStatus.duplicate_content
    assert duplicate.document_id == created.document_id
    assert duplicate.ingestion_job_id == created.ingestion_job_id
    assert duplicate.ingestion_in_progress
    assert not duplicate.ingestion_required
    assert repository.document_count == 1
    assert repository.job_count == 1
    assert repository.get_document(created.document_id).original_filename == "first.pdf"


def test_completed_duplicate_skips_ingestion_and_reuses_completed_job():
    repository = InMemoryFileIngestionRepository()
    service = FileIngestionService(repository)
    created = service.submit(request())
    repository.set_job_status(created.ingestion_job_id, IngestionStatus.completed)

    duplicate = service.submit(request(filename="copy.pdf"))

    assert duplicate.content_status is ContentStatus.duplicate_content
    assert duplicate.deduplicated
    assert not duplicate.ingestion_required
    assert not duplicate.ingestion_in_progress
    assert duplicate.ingestion_job_id == created.ingestion_job_id
    assert repository.job_count == 1


@pytest.mark.parametrize("terminal", [IngestionStatus.failed, IngestionStatus.cancelled])
def test_failed_or_cancelled_content_creates_recovery_job_without_duplicate_document(terminal):
    repository = InMemoryFileIngestionRepository()
    service = FileIngestionService(repository)
    created = service.submit(request())
    repository.set_job_status(created.ingestion_job_id, terminal)

    recovered = service.submit(request())

    assert recovered.content_status is ContentStatus.duplicate_content
    assert recovered.ingestion_required
    assert recovered.ingestion_job_id != created.ingestion_job_id
    assert repository.document_count == 1
    assert repository.job_count == 2


def test_most_recent_failed_reindex_recovers_even_when_an_older_job_completed():
    repository = InMemoryFileIngestionRepository()
    service = FileIngestionService(repository)
    created = service.submit(request())
    repository.set_job_status(created.ingestion_job_id, IngestionStatus.completed)
    reindex = service.submit(request(force_reindex=True))
    repository.set_job_status(reindex.ingestion_job_id, IngestionStatus.failed)

    recovered = service.submit(request())

    assert recovered.ingestion_required
    assert recovered.ingestion_job_id not in {
        created.ingestion_job_id,
        reindex.ingestion_job_id,
    }
    assert repository.job_count == 3


def test_forced_reindex_reuses_document_and_creates_new_job_for_identical_content():
    repository = InMemoryFileIngestionRepository()
    service = FileIngestionService(repository)
    created = service.submit(request())
    repository.set_job_status(created.ingestion_job_id, IngestionStatus.completed)

    reindexed = service.submit(request(force_reindex=True))

    assert reindexed.content_status is ContentStatus.forced_reindex
    assert reindexed.document_id == created.document_id
    assert reindexed.ingestion_required
    assert reindexed.force_reindex
    assert repository.document_count == 1
    assert repository.job_count == 2


def test_changed_bytes_for_known_document_are_modified_and_preserve_document_identity():
    repository = InMemoryFileIngestionRepository()
    service = FileIngestionService(repository)
    created = service.submit(request(content=b"version one"))
    repository.set_job_status(created.ingestion_job_id, IngestionStatus.completed)

    modified = service.submit(request(content=b"version two", document_id=created.document_id))

    assert modified.content_status is ContentStatus.modified_content
    assert modified.document_id == created.document_id
    assert modified.ingestion_required
    assert repository.document_count == 1
    assert repository.job_count == 2


def test_identical_bytes_do_not_deduplicate_across_visibility_scopes():
    repository = InMemoryFileIngestionRepository()
    service = FileIngestionService(repository)

    user = service.submit(request(roles=("user",)))
    admin = service.submit(request(roles=("admin",)))

    assert admin.content_status is ContentStatus.new_content
    assert admin.document_id != user.document_id
    assert repository.document_count == 2


def test_filename_and_mime_metadata_do_not_change_exact_content_identity():
    repository = InMemoryFileIngestionRepository()
    service = FileIngestionService(repository)

    first = service.submit(request(filename="original.pdf", mime_type="application/pdf"))
    duplicate = service.submit(
        request(filename="renamed.bin", mime_type="application/octet-stream")
    )

    assert duplicate.document_id == first.document_id
    assert repository.document_count == 1
    canonical = repository.get_document(first.document_id)
    assert canonical.original_filename == "original.pdf"
    assert canonical.mime_type == "application/pdf"


def test_matching_checksum_with_different_size_is_not_treated_as_duplicate():
    repository = InMemoryFileIngestionRepository()
    service = FileIngestionService(repository)
    first_request = request()
    first = service.submit(first_request)
    different_size = replace(
        first_request,
        fingerprint=FileFingerprint(
            "sha256",
            first_request.fingerprint.checksum,
            first_request.fingerprint.file_size_bytes + 1,
        ),
    )

    second = service.submit(different_size)

    assert second.content_status is ContentStatus.new_content
    assert second.document_id != first.document_id
    assert repository.document_count == 2


def test_idempotency_replay_includes_checksum_and_force_intent():
    repository = InMemoryFileIngestionRepository()
    service = FileIngestionService(repository)
    first_request = request(idempotency_key="upload-123", force_reindex=True)

    first = service.submit(first_request)
    replay = service.submit(first_request)

    assert replay.ingestion_job_id == first.ingestion_job_id
    assert repository.job_count == 1
    with pytest.raises(IdempotentFileRequestConflict):
        service.submit(replace(first_request, force_reindex=False))
    with pytest.raises(IdempotentFileRequestConflict):
        service.submit(request(content=b"changed", idempotency_key="upload-123"))


def test_no_op_duplicate_still_reserves_idempotency_key_against_different_content():
    repository = InMemoryFileIngestionRepository()
    service = FileIngestionService(repository)
    created = service.submit(request())
    repository.set_job_status(created.ingestion_job_id, IngestionStatus.completed)

    duplicate = service.submit(request(idempotency_key="duplicate-123"))
    replay = service.submit(request(idempotency_key="duplicate-123"))

    assert replay == duplicate
    assert repository.job_count == 1
    with pytest.raises(IdempotentFileRequestConflict):
        service.submit(request(content=b"different", idempotency_key="duplicate-123"))
