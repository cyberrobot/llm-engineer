import logging
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, ConfigDict

from assistant.api.dependencies import get_ingestion_operational_status_repository
from assistant.api.ingest import require_ingest_api_key
from assistant.infrastructure.repositories.ingestion_observability import (
    IngestionOperationalStatusRepository,
)
from core.metrics import ingestion_operational_metrics

router = APIRouter(prefix="/internal/ingestion", tags=["internal ingestion"])
logger = logging.getLogger(__name__)


class IngestionOperationalStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    queued_jobs: int
    running_jobs: int
    recoverable_jobs: int
    oldest_queued_age_seconds: float
    workers_observed: int


@router.get("/status", response_model=IngestionOperationalStatusResponse)
def get_ingestion_operational_status(
    repository: Annotated[
        IngestionOperationalStatusRepository,
        Depends(get_ingestion_operational_status_repository),
    ],
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> IngestionOperationalStatusResponse:
    require_ingest_api_key(x_api_key)
    status = repository.get(now=datetime.now(timezone.utc))
    try:
        ingestion_operational_metrics.observe_status(
            queued=status.queued_jobs,
            running=status.running_jobs,
            recoverable=status.recoverable_jobs,
            oldest_queued_age=status.oldest_queued_age_seconds,
            workers_active=status.workers_observed,
        )
    except Exception:
        # Metrics are derived output and never gate the authoritative status response.
        logger.warning("ingestion_telemetry_export_failed", extra={"reason": "observe_status"})
    return IngestionOperationalStatusResponse.model_validate(status, from_attributes=True)
