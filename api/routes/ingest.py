import os
import uuid

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from api.core.rate_limit import limiter
from api.services.embeddings import get_embedding
from api.services.storage import (
    list_all_chunks,
    save_chunk,
    save_document,
)

router = APIRouter()

DISABLE_INGEST = os.getenv("DISABLE_INGEST", "false").lower() == "true"


class IngestRequest(BaseModel):
    text: str
    doc_type: str = "general"
    access_roles: list[str] = ["user"]


def chunk_text(text: str, size: int = 500):
    return [text[i : i + size] for i in range(0, len(text), size)]


@router.post("/ingest")
@limiter.limit("5/minute")
def ingest(request: Request, body: IngestRequest):
    if DISABLE_INGEST:
        raise HTTPException(
            status_code=403, detail="Ingest endpoint is disabled in this environment."
        )
    doc_id = str(uuid.uuid4())

    save_document(doc_id, body.doc_type, body.access_roles)

    chunks = chunk_text(body.text)

    for chunk in chunks:
        save_chunk(
            chunk_id=str(uuid.uuid4()),
            doc_id=doc_id,
            text=chunk,
            embedding=get_embedding(chunk),
            access_roles=body.access_roles,
        )

    return {"doc_id": doc_id, "chunks_created": len(chunks)}


@router.get("/chunks")
def get_chunks():
    return list_all_chunks()


class SearchRequest(BaseModel):
    query: str = Query(..., description="Search query")
    access_role: str = Query("user", description="Access role for filtering results")
