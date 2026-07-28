from fastapi import APIRouter

from assistant.api.audit import router as audit_router
from assistant.api.ingest import router as ingest_router
from assistant.api.rag import router as rag_router

router = APIRouter()
router.include_router(ingest_router)
router.include_router(rag_router)
router.include_router(audit_router)


@router.get("/assistant/health", tags=["assistant"])
def health_check():
    return {"status": "ok"}
