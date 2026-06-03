import os

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from api.core.rate_limit import limiter
from api.services.ingest_document import ingest_document
from api.services.storage import (
    list_all_chunks,
)

router = APIRouter()

DISABLE_INGEST = os.getenv("DISABLE_INGEST", "false").lower() == "true"


class IngestRequest(BaseModel):
    text: str
    doc_type: str = "general"
    access_roles: list[str] = ["user"]


@router.post("/ingest")
@limiter.limit("5/minute")
def ingest(request: Request, body: IngestRequest):
    if DISABLE_INGEST:
        raise HTTPException(
            status_code=403, detail="Ingest endpoint is disabled in this environment."
        )

    return ingest_document(text=body.text, doc_type=body.doc_type, access_roles=body.access_roles)


@router.get("/chunks")
def get_chunks():
    return list_all_chunks()


class SearchRequest(BaseModel):
    query: str = Query(..., description="Search query")
    access_role: str = Query("user", description="Access role for filtering results")
