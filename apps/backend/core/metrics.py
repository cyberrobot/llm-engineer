from prometheus_client import REGISTRY, CollectorRegistry, Counter, Histogram


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
