from fastapi import APIRouter, HTTPException

from core.health import DependencyHealthError, validate_dependency_health

router = APIRouter()


@router.get("/health")
def health_check():
    try:
        validate_dependency_health()
    except DependencyHealthError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"status": "healthy"}
