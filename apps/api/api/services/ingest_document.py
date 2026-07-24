import uuid

from api.services.embeddings import get_embeddings
from api.services.storage import save_document_with_chunks


def ingest_document(text: str, doc_type: str, access_roles: list[str]) -> dict:
    doc_id = str(uuid.uuid4())
    chunks = chunk_text(text)

    embeddings = get_embeddings(chunks)

    chunk_rows = [
        {
            "id": str(uuid.uuid4()),
            "doc_id": doc_id,
            "text": chunk,
            "embedding": embedding,
            "access_roles": access_roles,
        }
        for chunk, embedding in zip(chunks, embeddings, strict=False)
    ]

    save_document_with_chunks(doc_id, doc_type, access_roles, chunk_rows)

    return {"doc_id": doc_id, "chunks_created": len(chunks)}


def chunk_text(text: str, size: int = 500):
    return [text[i : i + size] for i in range(0, len(text), size)]
