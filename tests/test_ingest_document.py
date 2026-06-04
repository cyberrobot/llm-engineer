from unittest.mock import patch

from api.services.ingest_document import ingest_document


def test_batches_embeddings_and_persists_chunks():
    text = ("a" * 500) + "b"
    access_roles = ["user", "manager"]
    embeddings = [[0.1, 0.2], [0.3, 0.4]]

    with (
        patch(
            "api.services.ingest_document.uuid.uuid4",
            side_effect=["doc-id", "chunk-id-1", "chunk-id-2"],
        ),
        patch(
            "api.services.ingest_document.get_embeddings",
            return_value=embeddings,
        ) as get_embeddings,
        patch("api.services.ingest_document.save_document_with_chunks") as save_document_with_chunks,
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
    )
