from fastapi import APIRouter, HTTPException

from assistant.api.assistant_admin import router as assistant_admin_router
from assistant.api.audit import router as audit_router
from assistant.api.chat import router as chat_router
from assistant.api.ingest import router as ingest_router
from assistant.api.ingestion_jobs import router as ingestion_jobs_router
from assistant.api.ingestion_status import router as ingestion_status_router
from assistant.api.knowledge import router as knowledge_router
from assistant.api.knowledge_sources import router as knowledge_sources_router
from assistant.api.public_chat import router as public_chat_router
from assistant.api.rag import router as rag_router
from assistant.schemas import HealthResponse
from core.health import DependencyHealthError, validate_dependency_health

router = APIRouter()
router.include_router(chat_router)
router.include_router(assistant_admin_router)
router.include_router(ingest_router)
router.include_router(ingestion_jobs_router)
router.include_router(ingestion_status_router)
router.include_router(knowledge_router)
router.include_router(knowledge_sources_router)
router.include_router(rag_router)
router.include_router(audit_router)
router.include_router(public_chat_router)


@router.get(
    "/assistant/health",
    response_model=HealthResponse,
    summary="Check Assistant health",
    tags=["assistant"],
)
def health_check() -> HealthResponse:
    try:
        validate_dependency_health()
    except DependencyHealthError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return HealthResponse(status="ok")
