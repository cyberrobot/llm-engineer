import uuid

from fastapi import APIRouter, Query
from pydantic import BaseModel

from api.services.embeddings import get_embedding
from api.services.retrieval import search_chunks
from api.services.storage import (
    list_all_chunks,
    save_chunk,
    save_document,
)

router = APIRouter()


class IngestRequest(BaseModel):
    text: str
    doc_type: str = "general"
    access_roles: list[str] = ["user"]


def chunk_text(text: str, size: int = 500):
    return [text[i : i + size] for i in range(0, len(text), size)]


@router.post("/ingest")
def ingest(request: IngestRequest):
    doc_id = str(uuid.uuid4())

    save_document(doc_id, request.doc_type, request.access_roles)

    chunks = chunk_text(request.text)

    for chunk in chunks:
        save_chunk(
            chunk_id=str(uuid.uuid4()),
            doc_id=doc_id,
            text=chunk,
            embedding=get_embedding(chunk),
            access_roles=request.access_roles,
        )

    return {"doc_id": doc_id, "chunks_created": len(chunks)}


@router.get("/chunks")
def get_chunks():
    return list_all_chunks()


class SearchRequest(BaseModel):
    query: str = Query(..., description="Search query")
    access_role: str = Query("user", description="Access role for filtering results")


@router.get("/search")
def search(request: SearchRequest):
    results = search_chunks(request.query, request.access_role)

    return {"query": request.query, "results": results}
