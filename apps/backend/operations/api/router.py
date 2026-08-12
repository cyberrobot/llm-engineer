import logging
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends

from core.authentication import ApiPrincipal
from operations.api.administration_router import router as administration_router
from operations.api.dependencies import prevent_operations_caching, require_operations_read, utc_now
from operations.api.health_dependencies import get_health_service
from operations.api.models import (
    AdministrativeErrorResponse,
    OperationsHealthResponse,
    OperationsRootResponse,
)
from operations.application.health import HealthService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin/operations",
    tags=["Operations Administration"],
    dependencies=[Depends(require_operations_read), Depends(prevent_operations_caching)],
)
router.include_router(administration_router)


@router.get(
    "",
    response_model=OperationsRootResponse,
    response_model_exclude_none=True,
    responses={
        401: {"model": AdministrativeErrorResponse, "description": "Authentication required"},
        403: {"model": AdministrativeErrorResponse, "description": "Permission denied"},
    },
    summary="Describe the operations administration API",
    description="Requires administrative read access.",
)
def get_operations_root(
    principal: Annotated[ApiPrincipal, Depends(require_operations_read)],
    generated_at: Annotated[datetime, Depends(utc_now)],
) -> OperationsRootResponse:
    logger.info(
        "admin_route_accessed",
        extra={"access_level": "read", "principal_id": principal.identifier},
    )
    return OperationsRootResponse(
        generated_at=generated_at,
        capabilities=[
            "health",
            "cache",
            "audit",
            "maintenance",
            "jobs",
            "summary",
        ],
    )


@router.get(
    "/health",
    response_model=OperationsHealthResponse,
    response_model_exclude_none=True,
    responses={
        401: {"model": AdministrativeErrorResponse, "description": "Authentication required"},
        403: {"model": AdministrativeErrorResponse, "description": "Permission denied"},
    },
    summary="Inspect application and dependency health",
    description=(
        "Requires administrative read access. A successful diagnostic request returns 200 even "
        "when its payload reports degraded or unhealthy dependencies."
    ),
)
async def get_operations_health(
    principal: Annotated[ApiPrincipal, Depends(require_operations_read)],
    health_service: Annotated[HealthService, Depends(get_health_service)],
) -> OperationsHealthResponse:
    diagnostic = await health_service.diagnose()
    logger.info(
        "admin_route_accessed",
        extra={"access_level": "read", "principal_id": principal.identifier},
    )
    return OperationsHealthResponse(
        status=diagnostic.status,
        generated_at=diagnostic.generated_at,
        checks=list(diagnostic.checks),
    )
