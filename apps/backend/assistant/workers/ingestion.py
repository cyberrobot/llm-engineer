import logging
import signal
import sys
from datetime import datetime, timedelta, timezone
from threading import Event, Thread

from assistant.api.dependencies import (
    build_ingestion_pipeline_runner,
    get_ai_provider,
    get_content_extractor,
    get_content_processing_service,
    get_ingestion_failure_classifier,
    get_ingestion_pipeline_definition,
    get_ingestion_retry_policy,
    get_ingestion_retry_sleeper,
    get_ingestion_step_execution_repository,
    get_knowledge_persistence_repository,
    get_knowledge_persistence_service,
    get_text_chunker,
    get_text_cleaner,
    get_website_loader,
)
from assistant.application.ingestion_worker import (
    IngestionJobClaim,
    IngestionWorker,
    WorkerExecutionResult,
)
from assistant.infrastructure.repositories.ingestion_worker import (
    FencedPostgresDocumentIngestionJobRepository,
    IngestionOwnershipLost,
    PostgresIngestionWorkerRepository,
)
from core.config import DATABASE_URL, get_ingestion_worker_settings, validate_startup_configuration
from core.logging import configure_logging
from infrastructure.database.connection import init_db

logger = logging.getLogger(__name__)


class PipelineClaimExecutor:
    def __init__(
        self,
        worker_repository: PostgresIngestionWorkerRepository,
        *,
        lease_duration: timedelta,
        heartbeat_interval_seconds: float,
    ) -> None:
        self._worker_repository = worker_repository
        self._lease_duration = lease_duration
        self._heartbeat_interval_seconds = heartbeat_interval_seconds
        self._shutdown = Event()

    def shutdown(self) -> None:
        """Stop renewing unfinished claims after the configured shutdown grace expires."""
        self._shutdown.set()

    def __call__(self, claim: IngestionJobClaim) -> WorkerExecutionResult:
        heartbeat_stop = Event()
        ownership_lost = Event()
        heartbeat = Thread(
            target=self._heartbeat,
            args=(claim, heartbeat_stop, ownership_lost),
            name=f"ingestion-heartbeat-{claim.job_id}",
            daemon=True,
        )
        heartbeat.start()
        logger.info(
            "ingestion_job_execution_started",
            extra={
                "worker_id": claim.worker_id,
                "job_id": str(claim.job_id),
                "document_id": claim.document_id,
                "claim_version": claim.claim_version,
            },
        )
        try:
            if claim.recovered:
                get_ingestion_step_execution_repository().interrupt_running_attempts(claim.job_id)
            runner = _build_runner(FencedPostgresDocumentIngestionJobRepository(claim))
            result = runner.run(claim.job_id)
            if ownership_lost.is_set():
                logger.warning(
                    "ingestion_job_lease_lost",
                    extra={
                        "worker_id": claim.worker_id,
                        "job_id": str(claim.job_id),
                        "claim_version": claim.claim_version,
                    },
                )
                return WorkerExecutionResult.ownership_lost
            event = (
                "ingestion_job_execution_completed"
                if result.succeeded
                else "ingestion_job_execution_failed"
            )
            logger.info(
                event,
                extra={
                    "worker_id": claim.worker_id,
                    "job_id": str(claim.job_id),
                    "claim_version": claim.claim_version,
                    "status": result.status.value if result.status else None,
                },
            )
            return (
                WorkerExecutionResult.completed
                if result.succeeded
                else WorkerExecutionResult.failed
            )
        except IngestionOwnershipLost:
            logger.warning(
                "ingestion_job_lease_lost",
                extra={
                    "worker_id": claim.worker_id,
                    "job_id": str(claim.job_id),
                    "claim_version": claim.claim_version,
                },
            )
            return WorkerExecutionResult.ownership_lost
        finally:
            heartbeat_stop.set()
            heartbeat.join()

    def _heartbeat(self, claim: IngestionJobClaim, stop: Event, ownership_lost: Event) -> None:
        while not stop.is_set() and not self._shutdown.wait(self._heartbeat_interval_seconds):
            now = datetime.now(timezone.utc)
            try:
                renewed = self._worker_repository.renew_lease(claim, self._lease_duration, now)
            except Exception:
                logger.exception(
                    "ingestion_job_heartbeat_failed",
                    extra={
                        "worker_id": claim.worker_id,
                        "job_id": str(claim.job_id),
                        "claim_version": claim.claim_version,
                    },
                )
                continue
            if not renewed:
                ownership_lost.set()
                return
            logger.debug(
                "ingestion_job_heartbeat_succeeded",
                extra={
                    "worker_id": claim.worker_id,
                    "job_id": str(claim.job_id),
                    "claim_version": claim.claim_version,
                    "lease_expires_at": now + self._lease_duration,
                },
            )


def _build_runner(repository):
    website_loader = get_website_loader()
    content_processing = get_content_processing_service(
        get_content_extractor(), get_text_cleaner(), get_text_chunker()
    )
    persistence = get_knowledge_persistence_service(
        get_ai_provider(), get_knowledge_persistence_repository()
    )
    definition = get_ingestion_pipeline_definition(website_loader, content_processing, persistence)
    return build_ingestion_pipeline_runner(
        repository,
        definition,
        website_loader,
        content_processing,
        persistence,
        get_ingestion_failure_classifier(),
        get_ingestion_retry_policy(),
        get_ingestion_retry_sleeper(),
        get_ingestion_step_execution_repository(),
    )


def main() -> int:
    configure_logging()
    validate_startup_configuration()
    settings = get_ingestion_worker_settings()
    if "--health-check" in sys.argv[1:]:
        if not DATABASE_URL:
            raise RuntimeError("DATABASE_URL is required by the ingestion worker.")
        from infrastructure.database.connection import get_connection

        with get_connection() as connection:
            connection.execute("SELECT 1")
        return 0
    if not settings.enabled:
        logger.info("ingestion_worker_disabled", extra={"worker_id": settings.worker_id})
        return 0
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is required by the ingestion worker.")
    init_db()
    stop = Event()

    def request_stop(_signum, _frame) -> None:
        logger.info("ingestion_worker_stopping", extra={"worker_id": settings.worker_id})
        stop.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    repository = PostgresIngestionWorkerRepository()
    executor = PipelineClaimExecutor(
        repository,
        lease_duration=timedelta(seconds=settings.lease_seconds),
        heartbeat_interval_seconds=settings.heartbeat_interval_seconds,
    )
    worker = IngestionWorker(
        repository,
        executor,
        worker_id=settings.worker_id,
        lease_duration=timedelta(seconds=settings.lease_seconds),
        poll_interval_seconds=settings.poll_interval_seconds,
        wait=stop.wait,
        now=lambda: datetime.now(timezone.utc),
        concurrency=settings.concurrency,
        shutdown_grace_seconds=settings.shutdown_grace_seconds,
    )
    try:
        worker.run(stop)
        return 0
    finally:
        if get_website_loader.cache_info().currsize:
            loader = get_website_loader()
            close = getattr(loader, "close", None)
            if close is not None:
                close()
            get_website_loader.cache_clear()
        if get_ai_provider.cache_info().currsize:
            provider = get_ai_provider()
            close = getattr(provider, "close", None)
            if close is not None:
                close()
            get_ai_provider.cache_clear()


if __name__ == "__main__":
    raise SystemExit(main())
