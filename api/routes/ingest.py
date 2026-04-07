from fastapi import APIRouter, Query
from pydantic import BaseModel
import uuid
from api.services.embeddings import get_embedding, cosine_similarity

router = APIRouter()

DOCUMENTS = []
CHUNKS = []

class IngestRequest(BaseModel):
    text: str
    doc_type: str = "general"
    
def chunk_text(text: str, size: int = 500):
    return [text[i:i+size] for i in range(0, len(text), size)]

def search_chunks(query: str, limit: int = 3):
    query_embedding = get_embedding(query)
    results = []

    for chunk in CHUNKS:
        score = cosine_similarity(query_embedding, chunk["embedding"])
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
            "embedding": get_embedding(chunk)
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