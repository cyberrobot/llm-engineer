import logging
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends

from core.authentication import ApiPrincipal
from operations.api.dependencies import require_operations_read, utc_now
from operations.api.models import AdministrativeErrorResponse, OperationsRootResponse

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin/operations",
    tags=["Operations Administration"],
    dependencies=[Depends(require_operations_read)],
)


@router.get(
    "",
    response_model=OperationsRootResponse,
    response_model_exclude_none=True,
    responses={
        401: {"model": AdministrativeErrorResponse, "description": "Authentication required"},
        403: {"model": AdministrativeErrorResponse, "description": "Permission denied"},
    },
    summary="Describe the operations administration API",
    description="Requires administrative read access. No operational capabilities are enabled yet.",
)
def get_operations_root(
    principal: Annotated[ApiPrincipal, Depends(require_operations_read)],
    generated_at: Annotated[datetime, Depends(utc_now)],
) -> OperationsRootResponse:
    logger.info(
        "admin_route_accessed",
        extra={"access_level": "read", "principal_id": principal.identifier},
    )
    return OperationsRootResponse(generated_at=generated_at)
