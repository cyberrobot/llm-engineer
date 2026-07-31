from unittest.mock import patch

from assistant.application.ingest_document import ingest_document
from assistant.application.uploads import record_uploaded_document
from assistant.domain.assistant import REDMOOR_ASSISTANT_ID


def test_batches_embeddings_and_persists_chunks():
    text = ("a" * 500) + "b"
    access_roles = ["user", "manager"]
    embeddings = [[0.1, 0.2], [0.3, 0.4]]

    with (
        patch(
            "assistant.application.ingest_document.uuid.uuid4",
            side_effect=["doc-id", "chunk-id-1", "chunk-id-2"],
        ),
        patch(
            "assistant.application.ingest_document.get_embeddings",
            return_value=embeddings,
        ) as get_embeddings,
        patch(
            "assistant.application.ingest_document.save_document_with_chunks"
        ) as save_document_with_chunks,
    ):
        result = ingest_document(
            text=text,
            doc_type="policy",
            access_roles=access_roles,
        )

    expected_chunks = ["a" * 500, "b"]
    expected_rows = [
        {
            "id": "chunk-id-1",
            "doc_id": "doc-id",
            "text": expected_chunks[0],
            "embedding": embeddings[0],
            "access_roles": access_roles,
        },
        {
            "id": "chunk-id-2",
            "doc_id": "doc-id",
            "text": expected_chunks[1],
            "embedding": embeddings[1],
            "access_roles": access_roles,
        },
    ]

    assert result == {"doc_id": "doc-id", "chunks_created": 2}
    get_embeddings.assert_called_once_with(expected_chunks)
    save_document_with_chunks.assert_called_once_with(
        "doc-id",
        "policy",
        access_roles,
        expected_rows,
        assistant_id=REDMOOR_ASSISTANT_ID,
    )


def test_record_uploaded_document_persists_document_and_ingestion_job():
    with (
        patch("assistant.application.uploads.create_uploaded_document_record") as create_document,
        patch("assistant.application.uploads.create_ingestion_job_record") as create_job,
    ):
        record_uploaded_document(
            "doc-id",
            "job-id",
            "policy",
            ["user", "admin"],
            "uploads/doc-id.pdf",
            "policy.pdf",
        )

    create_document.assert_called_once_with(
        "doc-id",
        "policy",
        ["user", "admin"],
        "uploads/doc-id.pdf",
        "policy.pdf",
        assistant_id=REDMOOR_ASSISTANT_ID,
    )
    create_job.assert_called_once_with(
        "job-id",
        "doc-id",
        stage="validate",
        status="queued",
        progress=0,
    )
