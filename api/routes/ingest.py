from fastapi import APIRouter
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