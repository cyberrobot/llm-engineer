from fastapi import APIRouter, HTTPException, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from core.health import DependencyHealthError, validate_dependency_health

router = APIRouter()


@router.get("/health")
def health_check():
    try:
        validate_dependency_health()
    except DependencyHealthError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"status": "healthy"}


@router.get("/health/live")
def liveness_check():
    return {"status": "alive"}


@router.get("/health/ready")
def readiness_check():
    try:
        validate_dependency_health()
    except DependencyHealthError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"status": "ready"}


@router.get("/metrics", include_in_schema=False)
def prometheus_metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
