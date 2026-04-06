from fastapi import APIRouter, Query
from pydantic import BaseModel
import uuid

router = APIRouter()

DOCUMENTS = []
CHUNKS = []

class IngestRequest(BaseModel):
    text: str
    doc_type: str = "general"
    
def chunk_text(text: str, size: int = 500):
    return [text[i:i+size] for i in range(0, len(text), size)]

def search_chunks(query: str, limit: int = 3):
    results = []

    query_lower = query.lower()

    for chunk in CHUNKS:
        text_lower = chunk["text"].lower()

        score = sum(1 for word in query_lower.split() if word in text_lower)

        if score > 0:
            results.append((score, chunk))

    results.sort(key=lambda x: x[0], reverse=True)

    return [chunk for _, chunk in results[:limit]]

@router.post("/ingest")
def ingest(request: IngestRequest):
    doc_id = str(uuid.uuid4())

    DOCUMENTS.append({
        "id": doc_id,
        "type": request.doc_type,
    })

    chunks = chunk_text(request.text)

    for chunk in chunks:
        CHUNKS.append({
            "id": str(uuid.uuid4()),
            "doc_id": doc_id,
            "text": chunk,
        })

    return {
        "doc_id": doc_id,
        "chunks_created": len(chunks)
    }

@router.get("/chunks")
def get_chunks():
    return CHUNKS

@router.get("/search")
def search(query: str = Query(..., description="Search query")):
    results = search_chunks(query)

    return {
        "query": query,
        "results": results
    }