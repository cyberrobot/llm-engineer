from fastapi import APIRouter

from assistant.api.audit import router as audit_router
from assistant.api.chat import router as chat_router
from assistant.api.ingest import router as ingest_router
from assistant.api.knowledge import router as knowledge_router
from assistant.api.rag import router as rag_router
from assistant.schemas import HealthResponse

router = APIRouter()
router.include_router(chat_router)
router.include_router(ingest_router)
router.include_router(knowledge_router)
router.include_router(rag_router)
router.include_router(audit_router)


@router.get(
    "/assistant/health",
    response_model=HealthResponse,
    summary="Check Assistant health",
    tags=["assistant"],
)
def health_check() -> HealthResponse:
    return HealthResponse(status="ok")
