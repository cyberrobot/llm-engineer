from typing import Any

from prometheus_client import REGISTRY, CollectorRegistry, Counter, Gauge, Histogram

from assistant.domain.document_ingestion_job import IngestionStep


class IngestionMetrics:
    """Prometheus instruments for stable, low-cardinality ingestion outcomes."""

    def __init__(self, *, registry: CollectorRegistry = REGISTRY) -> None:
        self.duration = Histogram(
            "ingestion_duration_seconds",
            "End-to-end knowledge ingestion duration.",
            registry=registry,
        )
        self.website_duration = Histogram(
            "ingestion_website_loading_duration_seconds",
            "Website loading duration for ingestion.",
            registry=registry,
        )
        self.processing_duration = Histogram(
            "ingestion_processing_duration_seconds",
            "Content processing duration for ingestion.",
            registry=registry,
        )
        self.persistence_duration = Histogram(
            "ingestion_persistence_duration_seconds",
            "Knowledge persistence duration for ingestion.",
            registry=registry,
        )
        self.embedding_duration = Histogram(
            "ingestion_embedding_duration_seconds",
            "Embedding generation duration for ingestion.",
            registry=registry,
        )
        self.success = Counter(
            "ingestion_success_total", "Completed ingestions.", registry=registry
        )
        self.failure = Counter("ingestion_failure_total", "Failed ingestions.", registry=registry)
        self.pages_processed = Counter(
            "ingestion_pages_processed_total", "Website pages processed.", registry=registry
        )
        self.pages_skipped = Counter(
            "ingestion_pages_skipped_total", "Website pages skipped.", registry=registry
        )
        self.documents_persisted = Counter(
            "ingestion_documents_persisted_total",
            "Knowledge documents created or updated.",
            registry=registry,
        )
        self.chunks_persisted = Counter(
            "ingestion_chunks_persisted_total", "Knowledge chunks persisted.", registry=registry
        )
        self.embeddings_generated = Counter(
            "ingestion_embeddings_generated_total",
            "Embedding vectors generated.",
            registry=registry,
        )

    def record_failure(
        self,
        *,
        total_duration_ms: int,
        website_duration_ms: int = 0,
        processing_duration_ms: int = 0,
        persistence_duration_ms: int = 0,
    ) -> None:
        self.failure.inc()
        self.duration.observe(total_duration_ms / 1_000)
        self.website_duration.observe(website_duration_ms / 1_000)
        self.processing_duration.observe(processing_duration_ms / 1_000)
        self.persistence_duration.observe(persistence_duration_ms / 1_000)

    def record_success(
        self,
        *,
        total_duration_ms: int,
        website_duration_ms: int,
        processing_duration_ms: int,
        persistence_duration_ms: int,
        embedding_duration_ms: int,
        pages_processed: int,
        pages_skipped: int,
        documents_persisted: int,
        chunks_persisted: int,
        embeddings_generated: int,
    ) -> None:
        self.success.inc()
        self.duration.observe(total_duration_ms / 1_000)
        self.website_duration.observe(website_duration_ms / 1_000)
        self.processing_duration.observe(processing_duration_ms / 1_000)
        self.persistence_duration.observe(persistence_duration_ms / 1_000)
        self.embedding_duration.observe(embedding_duration_ms / 1_000)
        self.pages_processed.inc(pages_processed)
        self.pages_skipped.inc(pages_skipped)
        self.documents_persisted.inc(documents_persisted)
        self.chunks_persisted.inc(chunks_persisted)
        self.embeddings_generated.inc(embeddings_generated)


ingestion_metrics = IngestionMetrics()


class AdministratorAuthenticationMetrics:
    """Bounded authentication counters without identity or network labels."""

    def __init__(self, *, registry: CollectorRegistry = REGISTRY) -> None:
        self.login_attempts = Counter(
            "admin_login_attempts_total", "Administrator login attempts.", registry=registry
        )
        self.login_successes = Counter(
            "admin_login_successes_total", "Successful administrator logins.", registry=registry
        )
        self.login_failures = Counter(
            "admin_login_failures_total", "Failed administrator logins.", registry=registry
        )
        self.login_throttled = Counter(
            "admin_login_throttled_total", "Throttled administrator logins.", registry=registry
        )
        self.sessions_created = Counter(
            "admin_sessions_created_total", "Administrator sessions created.", registry=registry
        )
        self.sessions_revoked = Counter(
            "admin_sessions_revoked_total", "Administrator sessions revoked.", registry=registry
        )


administrator_authentication_metrics = AdministratorAuthenticationMetrics()


class KnowledgeSourceMetrics:
    """Knowledge-source lifecycle counters without user-controlled labels."""

    def __init__(self, *, registry: CollectorRegistry = REGISTRY) -> None:
        self.created = Counter(
            "knowledge_source_created_total", "Created knowledge sources.", registry=registry
        )
        self.reingested = Counter(
            "knowledge_source_reingested_total", "Queued source re-ingestions.", registry=registry
        )
        self.replayed = Counter(
            "knowledge_source_replayed_total",
            "Idempotent source request replays.",
            registry=registry,
        )
        self.duplicate_urls = Counter(
            "knowledge_source_duplicate_url_rejections_total",
            "Duplicate source URL submissions.",
            registry=registry,
        )
        self.deleted = Counter(
            "knowledge_source_deleted_total", "Deleted knowledge sources.", registry=registry
        )
        self.retrieval_enabled = Counter(
            "knowledge_source_retrieval_enabled_total",
            "Knowledge sources enabled for retrieval.",
            registry=registry,
        )
        self.retrieval_disabled = Counter(
            "knowledge_source_retrieval_disabled_total",
            "Knowledge sources disabled for retrieval.",
            registry=registry,
        )


knowledge_source_metrics = KnowledgeSourceMetrics()


class AssistantAdministrationMetrics:
    def __init__(self, *, registry: CollectorRegistry = REGISTRY) -> None:
        self.operations = Counter(
            "assistant_admin_operations_total",
            "Assistant administration operations by bounded operation and outcome.",
            ("operation", "outcome"),
            registry=registry,
        )


assistant_administration_metrics = AssistantAdministrationMetrics()


class PublicAssistantChatMetrics:
    """Public-chat metrics without user-controlled or high-cardinality labels."""

    def __init__(self, *, registry: CollectorRegistry = REGISTRY) -> None:
        self.requests = Counter(
            "public_chat_requests_total", "Prepared public chat requests.", registry=registry
        )
        self.completed = Counter(
            "public_chat_completed_total", "Completed public chat streams.", registry=registry
        )
        self.insufficient = Counter(
            "public_chat_insufficient_knowledge_total",
            "Public chats answered with the fixed insufficient-knowledge response.",
            registry=registry,
        )
        self.failures = Counter(
            "public_chat_failures_total", "Failed public chat streams.", registry=registry
        )
        self.cancelled = Counter(
            "public_chat_cancelled_total", "Cancelled public chat streams.", registry=registry
        )
        self.rate_limit_rejections = Counter(
            "public_chat_rate_limit_rejections_total",
            "Rejected public chat requests by configured rate limits.",
            registry=registry,
        )
        self.origin_rejections = Counter(
            "public_chat_origin_rejections_total",
            "Rejected public chat browser origins.",
            registry=registry,
        )
        self.payload_rejections = Counter(
            "public_chat_payload_rejections_total",
            "Rejected public chat request payloads.",
            registry=registry,
        )
        self.input_limit_rejections = Counter(
            "public_chat_input_limit_rejections_total",
            "Rejected public chat token budgets.",
            registry=registry,
        )
        self.concurrency_rejections = Counter(
            "public_chat_concurrency_rejections_total",
            "Rejected public chat concurrency acquisitions.",
            ("reason",),
            registry=registry,
        )
        self.timeouts = Counter(
            "public_chat_timeouts_total", "Timed out public chats.", registry=registry
        )
        self.active = Gauge(
            "public_chat_active_requests",
            "Active public chat streams on this instance.",
            registry=registry,
        )
        self.request_bytes = Histogram(
            "public_chat_request_bytes",
            "Accepted and rejected public chat request sizes.",
            registry=registry,
        )
        self.estimated_input_tokens = Histogram(
            "public_chat_estimated_input_tokens",
            "Conservatively estimated public chat prompt tokens.",
            registry=registry,
        )
        self.estimated_output_tokens = Histogram(
            "public_chat_output_tokens",
            "Conservative estimated public chat output tokens.",
            registry=registry,
        )
        self.time_to_first_token = Histogram(
            "public_chat_time_to_first_token_seconds",
            "Public chat time from request preparation to first model delta.",
            registry=registry,
        )
        self.retrieval_duration = Histogram(
            "public_chat_retrieval_duration_seconds",
            "Public chat retrieval duration.",
            registry=registry,
        )
        self.generation_duration = Histogram(
            "public_chat_generation_duration_seconds",
            "Public chat generation duration.",
            registry=registry,
        )
        self.total_duration = Histogram(
            "public_chat_total_duration_seconds",
            "Total public chat stream duration.",
            registry=registry,
        )


public_chat_metrics = PublicAssistantChatMetrics()


class IngestionOperationalMetrics:
    """Job/worker metrics whose labels are deliberately bounded enumerations."""

    def __init__(self, *, registry: CollectorRegistry = REGISTRY) -> None:
        self.jobs_created = Counter(
            "ingestion_jobs_created_total", "Durably created ingestion jobs.", registry=registry
        )
        self.jobs_completed = Counter(
            "ingestion_jobs_completed_total", "Durably completed ingestion jobs.", registry=registry
        )
        self.jobs_failed = Counter(
            "ingestion_jobs_failed_total", "Durably failed ingestion jobs.", registry=registry
        )
        self.jobs_recovered = Counter(
            "ingestion_jobs_recovered_total", "Recovered expired job leases.", registry=registry
        )
        self.jobs_claimed = Counter(
            "ingestion_jobs_claimed_total", "Worker job claims.", registry=registry
        )
        self.step_attempts = Counter(
            "ingestion_step_attempts_total",
            "Ingestion step attempts.",
            ("step",),
            registry=registry,
        )
        self.step_retries = Counter(
            "ingestion_step_retries_total",
            "Scheduled ingestion retries.",
            ("step", "failure_category"),
            registry=registry,
        )
        self.lease_losses = Counter(
            "worker_lease_losses_total", "Worker lease ownership losses.", registry=registry
        )
        self.persistence_rollbacks = Counter(
            "ingestion_persistence_rollbacks_total",
            "Rolled-back ingestion persistence transactions.",
            registry=registry,
        )
        self.duplicates = Counter(
            "ingestion_duplicates_total",
            "Deduplicated ingestion submissions.",
            ("content_status",),
            registry=registry,
        )
        self.pipeline_skipped = Counter(
            "ingestion_pipeline_skipped_total",
            "Ingestion pipelines skipped after preflight.",
            ("content_status",),
            registry=registry,
        )
        self.forced_reindexes = Counter(
            "ingestion_forced_reindex_total",
            "Forced ingestion re-index submissions.",
            registry=registry,
        )
        self.queued = Gauge(
            "ingestion_jobs_queued", "Queued jobs from authoritative storage.", registry=registry
        )
        self.running = Gauge(
            "ingestion_jobs_running", "Running jobs from authoritative storage.", registry=registry
        )
        self.recoverable = Gauge(
            "ingestion_recoverable_jobs",
            "Running jobs with an expired lease.",
            registry=registry,
        )
        self.oldest_queued_age = Gauge(
            "ingestion_oldest_queued_age_seconds",
            "Age of the oldest queued ingestion job.",
            registry=registry,
        )
        self.workers_active = Gauge(
            "ingestion_workers_active",
            "Workers inferred from active unexpired job leases.",
            registry=registry,
        )
        self.queue_wait = Histogram(
            "ingestion_queue_wait_seconds", "Queue wait duration.", registry=registry
        )
        self.job_processing = Histogram(
            "ingestion_job_processing_duration_seconds",
            "Background job processing duration.",
            registry=registry,
        )
        self.total_duration = Histogram(
            "ingestion_total_duration_seconds",
            "Total queued-to-terminal duration.",
            registry=registry,
        )
        self.step_duration = Histogram(
            "ingestion_step_duration_seconds",
            "Ingestion step attempt duration.",
            ("step",),
            registry=registry,
        )
        self.worker_execution = Histogram(
            "worker_job_execution_duration_seconds",
            "Worker claim execution duration.",
            registry=registry,
        )

    def job_created(self) -> None:
        self.jobs_created.inc()

    def job_completed(
        self, *, queue_wait_seconds: float, processing_seconds: float, total_seconds: float
    ) -> None:
        self.jobs_completed.inc()
        self.queue_wait.observe(max(0, queue_wait_seconds))
        self.job_processing.observe(max(0, processing_seconds))
        self.total_duration.observe(max(0, total_seconds))

    def job_failed(self) -> None:
        self.jobs_failed.inc()

    def job_recovered(self) -> None:
        self.jobs_recovered.inc()

    def job_claimed(self) -> None:
        self.jobs_claimed.inc()

    def worker_executed(self, duration_seconds: float) -> None:
        self.worker_execution.observe(max(0, duration_seconds))

    def lease_lost(self) -> None:
        self.lease_losses.inc()

    def persistence_rolled_back(self) -> None:
        self.persistence_rollbacks.inc()

    def duplicate(self, content_status: str, *, pipeline_skipped: bool) -> None:
        self.duplicates.labels(content_status=content_status).inc()
        if pipeline_skipped:
            self.pipeline_skipped.labels(content_status=content_status).inc()

    def forced_reindex(self) -> None:
        self.forced_reindexes.inc()

    def step_attempt_started(self, step: IngestionStep) -> None:
        self.step_attempts.labels(step=step.value).inc()

    def step_attempt_completed(self, step: IngestionStep, duration_seconds: float) -> None:
        self.step_duration.labels(step=step.value).observe(max(0, duration_seconds))

    def step_retry(self, step: IngestionStep, failure_category: str) -> None:
        self.step_retries.labels(step=step.value, failure_category=failure_category).inc()

    def observe_status(
        self,
        *,
        queued: int,
        running: int,
        recoverable: int,
        oldest_queued_age: float,
        workers_active: int = 0,
    ) -> None:
        self.queued.set(max(0, queued))
        self.running.set(max(0, running))
        self.recoverable.set(max(0, recoverable))
        self.oldest_queued_age.set(max(0, oldest_queued_age))
        self.workers_active.set(max(0, workers_active))


ingestion_operational_metrics = IngestionOperationalMetrics()


class IngestionMaintenanceMetrics:
    """Maintenance telemetry with category, outcome, and reason-only labels."""

    def __init__(self, *, registry: CollectorRegistry = REGISTRY) -> None:
        self.runs = Counter(
            "ingestion_maintenance_runs_total",
            "Ingestion maintenance runs.",
            ("maintenance_category", "result"),
            registry=registry,
        )
        self.records_deleted = Counter(
            "ingestion_maintenance_records_deleted_total",
            "Records deleted by ingestion maintenance.",
            ("maintenance_category",),
            registry=registry,
        )
        self.records_archived = Counter(
            "ingestion_maintenance_records_archived_total",
            "Records archived by ingestion maintenance.",
            ("maintenance_category",),
            registry=registry,
        )
        self.records_repaired = Counter(
            "ingestion_maintenance_records_repaired_total",
            "Records repaired by ingestion maintenance.",
            ("maintenance_category",),
            registry=registry,
        )
        self.records_skipped = Counter(
            "ingestion_maintenance_records_skipped_total",
            "Records skipped by ingestion maintenance.",
            ("maintenance_category",),
            registry=registry,
        )
        self.errors = Counter(
            "ingestion_maintenance_errors_total",
            "Safe ingestion maintenance error codes.",
            ("maintenance_category", "reason_code"),
            registry=registry,
        )
        self.manual_review = Counter(
            "ingestion_maintenance_manual_review_total",
            "Maintenance findings requiring manual review.",
            ("maintenance_category", "reason_code"),
            registry=registry,
        )
        self.run_duration = Histogram(
            "ingestion_maintenance_run_duration_seconds",
            "Maintenance run duration.",
            ("maintenance_category",),
            registry=registry,
        )
        self.batch_duration = Histogram(
            "ingestion_maintenance_batch_duration_seconds",
            "Maintenance batch duration.",
            ("maintenance_category",),
            registry=registry,
        )

    def record_batch(self, category: str, duration_seconds: float) -> None:
        self.batch_duration.labels(maintenance_category=category).observe(max(0, duration_seconds))

    def record_result(self, result: Any, *, outcome: str) -> None:
        category = result.maintenance_category.value
        self.runs.labels(maintenance_category=category, result=outcome).inc()
        self.records_deleted.labels(maintenance_category=category).inc(result.records_deleted)
        self.records_archived.labels(maintenance_category=category).inc(result.records_archived)
        self.records_repaired.labels(maintenance_category=category).inc(result.records_repaired)
        self.records_skipped.labels(maintenance_category=category).inc(result.records_skipped)
        self.run_duration.labels(maintenance_category=category).observe(
            max(0, result.duration_ms) / 1_000
        )
        for error in result.errors:
            self.errors.labels(maintenance_category=category, reason_code=error.code).inc()
        for finding in result.findings:
            self.manual_review.labels(
                maintenance_category=category, reason_code=finding.reason_code
            ).inc()


ingestion_maintenance_metrics = IngestionMaintenanceMetrics()
