import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response, status
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel, ConfigDict

from operations.api.administration_dependencies import get_maintenance_service
from operations.api.health_dependencies import get_health_service
from operations.application.administration import MaintenanceService
from operations.application.health import HealthService
from operations.domain.administration import OperationsDependencyUnavailable

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Health"])


class LivenessResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["alive"] = "alive"


class ReadinessResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["ready", "not_ready"]


class LegacyHealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["healthy", "unhealthy"]


@router.get(
    "/health/live",
    response_model=LivenessResponse,
    summary="Check process liveness",
    description="Public infrastructure probe with no external dependency access.",
)
async def liveness() -> LivenessResponse:
    return LivenessResponse()


@router.get(
    "/health/ready",
    response_model=ReadinessResponse,
    responses={503: {"model": ReadinessResponse, "description": "A required dependency failed"}},
    summary="Check application readiness",
    description="Public probe with a deliberately minimal response and no dependency details.",
)
async def readiness(
    response: Response,
    health_service: Annotated[HealthService, Depends(get_health_service)],
    maintenance_service: Annotated[MaintenanceService, Depends(get_maintenance_service)],
) -> ReadinessResponse:
    diagnostic = await health_service.diagnose()
    try:
        maintenance_enabled = maintenance_service.get().enabled
    except OperationsDependencyUnavailable:
        maintenance_enabled = True
    if maintenance_enabled or not diagnostic.ready:
        logger.warning(
            "readiness_check_failed",
            extra={"health_status": diagnostic.status.value},
        )
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ReadinessResponse(status="not_ready")
    return ReadinessResponse(status="ready")


@router.get(
    "/health",
    response_model=LegacyHealthResponse,
    responses={503: {"model": LegacyHealthResponse, "description": "Application is not ready"}},
    summary="Check application health (compatibility route)",
    description="Backward-compatible readiness-style route. New probes should use /health/ready.",
)
async def health_check(
    response: Response,
    health_service: Annotated[HealthService, Depends(get_health_service)],
    maintenance_service: Annotated[MaintenanceService, Depends(get_maintenance_service)],
) -> LegacyHealthResponse:
    diagnostic = await health_service.diagnose()
    try:
        maintenance_enabled = maintenance_service.get().enabled
    except OperationsDependencyUnavailable:
        maintenance_enabled = True
    if maintenance_enabled or not diagnostic.ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return LegacyHealthResponse(status="unhealthy")
    return LegacyHealthResponse(status="healthy")


@router.get("/metrics", include_in_schema=False)
def prometheus_metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
