"""Authenticated administrator HTTP adapter for the evaluation subsystem."""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ValidationError

from admin_auth.dependencies import require_administrator_role, require_trusted_admin_origin
from assistant.api.dependencies import get_evaluation_administration_service
from assistant.application.evaluation_admin import EvaluationAdministrationService
from assistant.evaluation import (
    EvaluationDatasetError,
    EvaluationDatasetJsonError,
    EvaluationDatasetReadError,
    EvaluationDatasetValidationError,
    EvaluationReportError,
    EvaluationReportExistsError,
    EvaluationReportJsonError,
    EvaluationReportPathError,
    EvaluationReportReadError,
    EvaluationReportValidationError,
    EvaluationReportWriteError,
    UnsupportedEvaluationDatasetSchemaError,
    UnsupportedEvaluationReportSchemaError,
)
from assistant.infrastructure.evaluation_files import (
    EvaluationDatasetResourceNotFound,
    EvaluationReportResourceNotFound,
    EvaluationResourceCatalogError,
    EvaluationResourceDirectoryError,
    InvalidEvaluationResourceIdentifier,
)
from assistant.schemas.evaluation_admin import (
    CompareEvaluationRunsRequest,
    EvaluationAdminErrorResponse,
    EvaluationComparisonResponse,
    EvaluationDatasetDetailResponse,
    EvaluationDatasetListResponse,
    EvaluationDatasetSummaryResponse,
    EvaluationExecutionResponse,
    EvaluationRunListItemResponse,
    EvaluationRunListResponse,
    EvaluationRunResponse,
    ExecuteEvaluationRequest,
)
from infrastructure.ai.exceptions import AIConfigurationError

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin/evaluation",
    tags=["administrator evaluation"],
    dependencies=[Depends(require_administrator_role)],
)

ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"model": EvaluationAdminErrorResponse, "description": "Authentication required"},
    403: {
        "model": EvaluationAdminErrorResponse,
        "description": "Administrator or trusted origin required",
    },
    404: {"model": EvaluationAdminErrorResponse, "description": "Resource not found"},
    409: {"model": EvaluationAdminErrorResponse, "description": "Evaluation conflict"},
    422: {"model": EvaluationAdminErrorResponse, "description": "Invalid evaluation resource"},
    500: {"model": EvaluationAdminErrorResponse, "description": "Evaluation operation failed"},
    503: {"model": EvaluationAdminErrorResponse, "description": "Evaluation unavailable"},
}

_MAPPED_ERRORS = (
    EvaluationDatasetError,
    EvaluationReportError,
    EvaluationDatasetResourceNotFound,
    EvaluationReportResourceNotFound,
    EvaluationResourceCatalogError,
    EvaluationResourceDirectoryError,
    InvalidEvaluationResourceIdentifier,
)


def _error(code: str, message: str, status_code: int) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def _map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, InvalidEvaluationResourceIdentifier):
        return _error(
            "invalid_evaluation_identifier",
            "The evaluation resource identifier is invalid.",
            422,
        )
    if isinstance(exc, EvaluationDatasetResourceNotFound):
        return _error(
            "evaluation_dataset_not_found",
            "Evaluation dataset not found.",
            404,
        )
    if isinstance(exc, EvaluationReportResourceNotFound):
        return _error(
            "evaluation_report_not_found",
            "Evaluation report not found.",
            404,
        )
    if isinstance(exc, UnsupportedEvaluationDatasetSchemaError):
        return _error(
            "unsupported_dataset_schema",
            "The evaluation dataset schema is not supported.",
            422,
        )
    if isinstance(exc, (EvaluationDatasetJsonError, EvaluationDatasetValidationError)):
        return _error(
            "malformed_evaluation_dataset",
            "The evaluation dataset is malformed.",
            422,
        )
    if isinstance(exc, EvaluationDatasetReadError):
        return _error(
            "evaluation_dataset_unavailable",
            "The evaluation dataset could not be read.",
            503,
        )
    if isinstance(exc, EvaluationDatasetError):
        return _error(
            "evaluation_dataset_unavailable",
            "The evaluation dataset is unavailable.",
            503,
        )
    if isinstance(exc, UnsupportedEvaluationReportSchemaError):
        return _error(
            "unsupported_report_schema",
            "The evaluation report schema is not supported.",
            422,
        )
    if isinstance(
        exc,
        (EvaluationReportJsonError, EvaluationReportValidationError, EvaluationReportReadError),
    ):
        return _error(
            "malformed_evaluation_report",
            "The evaluation report is malformed or unreadable.",
            422,
        )
    if isinstance(exc, EvaluationReportExistsError):
        return _error(
            "evaluation_report_exists",
            "An evaluation report with this identity already exists.",
            409,
        )
    if isinstance(exc, (EvaluationReportWriteError, EvaluationReportPathError)):
        return _error(
            "evaluation_report_persistence_failed",
            "The evaluation report could not be persisted.",
            500,
        )
    if isinstance(exc, EvaluationReportError):
        return _error(
            "evaluation_report_unavailable",
            "The evaluation report is unavailable.",
            503,
        )
    if isinstance(exc, (EvaluationResourceDirectoryError, EvaluationResourceCatalogError)):
        return _error(
            "evaluation_resources_unavailable",
            "Server-managed evaluation resources are unavailable.",
            503,
        )
    return _error("evaluation_operation_failed", "The evaluation operation failed.", 500)


@router.get(
    "/datasets",
    response_model=EvaluationDatasetListResponse,
    responses=ERROR_RESPONSES,
)
def list_datasets(
    service: Annotated[
        EvaluationAdministrationService, Depends(get_evaluation_administration_service)
    ],
) -> EvaluationDatasetListResponse:
    try:
        resources = service.list_datasets()
    except _MAPPED_ERRORS as exc:
        raise _map_error(exc) from exc
    items = [EvaluationDatasetSummaryResponse.from_resource(item) for item in resources]
    return EvaluationDatasetListResponse(items=items, total=len(items))


@router.get(
    "/datasets/{dataset_id:path}",
    response_model=EvaluationDatasetDetailResponse,
    responses=ERROR_RESPONSES,
)
def dataset_detail(
    dataset_id: str,
    service: Annotated[
        EvaluationAdministrationService, Depends(get_evaluation_administration_service)
    ],
) -> EvaluationDatasetDetailResponse:
    try:
        return EvaluationDatasetDetailResponse.from_resource(service.get_dataset(dataset_id))
    except _MAPPED_ERRORS as exc:
        raise _map_error(exc) from exc


@router.post(
    "/runs",
    response_model=EvaluationExecutionResponse,
    responses=ERROR_RESPONSES,
    dependencies=[Depends(require_trusted_admin_origin)],
    description=(
        "Executes one server-managed dataset synchronously and optionally persists one report "
        "to the configured server directory."
    ),
)
def execute_evaluation(
    request: ExecuteEvaluationRequest,
    service: Annotated[
        EvaluationAdministrationService, Depends(get_evaluation_administration_service)
    ],
) -> EvaluationExecutionResponse:
    try:
        result = service.execute(
            dataset_id=request.dataset_id,
            options=request.run_options(),
            persist_report=request.persist_report,
        )
    except _MAPPED_ERRORS as exc:
        raise _map_error(exc) from exc
    except ValidationError as exc:
        raise _error(
            "invalid_evaluation_options",
            "The evaluation options are invalid.",
            422,
        ) from exc
    except AIConfigurationError as exc:
        raise _error(
            "evaluation_bootstrap_failed",
            "Evaluation services could not be configured.",
            503,
        ) from exc
    logger.info(
        "administrator_evaluation_completed",
        extra={
            "run_id": result.run.id,
            "dataset_id": request.dataset_id,
            "evaluation_status": result.run.status.value,
            "case_count": len(result.run.results),
            "report_persisted": result.report_persisted,
        },
    )
    return EvaluationExecutionResponse(
        run=EvaluationRunResponse.from_domain(result.run),
        report_persisted=result.report_persisted,
    )


@router.get(
    "/runs",
    response_model=EvaluationRunListResponse,
    responses=ERROR_RESPONSES,
)
def list_runs(
    service: Annotated[
        EvaluationAdministrationService, Depends(get_evaluation_administration_service)
    ],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> EvaluationRunListResponse:
    try:
        runs, total = service.list_reports(limit=limit, offset=offset)
    except _MAPPED_ERRORS as exc:
        raise _map_error(exc) from exc
    return EvaluationRunListResponse(
        items=[EvaluationRunListItemResponse.from_domain(run) for run in runs],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/runs/{run_id:path}",
    response_model=EvaluationRunResponse,
    responses=ERROR_RESPONSES,
)
def run_detail(
    run_id: str,
    service: Annotated[
        EvaluationAdministrationService, Depends(get_evaluation_administration_service)
    ],
) -> EvaluationRunResponse:
    try:
        return EvaluationRunResponse.from_domain(service.get_report(run_id))
    except _MAPPED_ERRORS as exc:
        raise _map_error(exc) from exc


@router.post(
    "/comparisons",
    response_model=EvaluationComparisonResponse,
    responses=ERROR_RESPONSES,
    description="Compares two server-managed reports without modifying either report.",
)
def compare_runs(
    request: CompareEvaluationRunsRequest,
    service: Annotated[
        EvaluationAdministrationService, Depends(get_evaluation_administration_service)
    ],
) -> EvaluationComparisonResponse:
    try:
        comparison = service.compare(
            candidate_run_id=request.candidate_run_id,
            baseline_run_id=request.baseline_run_id,
            policy=request.policy(),
        )
    except _MAPPED_ERRORS as exc:
        raise _map_error(exc) from exc
    except ValidationError as exc:
        raise _error(
            "invalid_evaluation_options",
            "The evaluation comparison options are invalid.",
            422,
        ) from exc
    if not comparison.compatible:
        raise _error(
            "incompatible_evaluation_comparison",
            "The evaluation reports are not compatible.",
            409,
        )
    return EvaluationComparisonResponse.from_domain(comparison)
