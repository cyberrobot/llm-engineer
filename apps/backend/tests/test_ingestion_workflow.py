import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient

from assistant.api.dependencies import get_ingestion_service
from assistant.application.chat import ChatService
from assistant.application.content_processing_service import ContentProcessingService
from assistant.application.ingestion_retry import IngestionFailureClassifier, IngestionRetryPolicy
from assistant.application.ingestion_service import IngestionService
from assistant.application.knowledge_persistence_service import KnowledgePersistenceService
from assistant.application.retrieval_service import RetrievalService
from assistant.domain.assistant import REDMOOR_ASSISTANT_ID
from assistant.domain.knowledge_persistence import (
    KnowledgeDocumentRecord,
    KnowledgeWriteResult,
    PersistedKnowledgeChunk,
)
from assistant.infrastructure.ingestion.html_content_extractor import HtmlContentExtractor
from assistant.infrastructure.ingestion.normalising_text_cleaner import NormalisingTextCleaner
from assistant.infrastructure.ingestion.semantic_text_chunker import SemanticTextChunker
from assistant.infrastructure.ingestion.website_loader import HttpWebsiteLoader
from assistant.infrastructure.repositories import VectorKnowledgeRepository
from assistant.infrastructure.repositories.ingestion_job import (
    InMemoryIngestionJobRepository,
    PostgresIngestionJobRepository,
)
from assistant.infrastructure.repositories.knowledge_persistence import (
    PostgresKnowledgePersistenceRepository,
)
from assistant.infrastructure.vector_store import (
    InMemoryVectorEntry,
    InMemoryVectorStore,
    PgVectorStore,
    VectorRecord,
)
from assistant.schemas import ChatRequest
from core.config import DATABASE_URL, EMBEDDING_VECTOR_DIMENSIONS, IngestionRetrySettings
from infrastructure.ai.providers import AIProvider
from infrastructure.database.connection import get_connection, init_db

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "content_processing"
PUBLIC_IPS = ("93.184.216.34",)


class DeterministicEmbeddingProvider:
    def __init__(self, dimensions: int = 3) -> None:
        self.dimensions = dimensions
        self.batch_calls: list[list[str]] = []
        self.query_calls: list[str] = []

    def generate_embeddings(self, *, texts: list[str]) -> list[list[float]]:
        self.batch_calls.append(list(texts))
        return [[1.0] + [0.0] * (self.dimensions - 1) for _ in texts]

    def generate_embedding(self, *, text: str) -> list[float]:
        self.query_calls.append(text)
        return [1.0] + [0.0] * (self.dimensions - 1)


class RecordingCompletionProvider(AIProvider):
    def __init__(self) -> None:
        self.user_prompt: str | None = None

    @property
    def name(self) -> str:
        return "test"

    @property
    def model(self) -> str:
        return "test-model"

    def generate_response(self, *, system_prompt: str, user_prompt: str) -> str:
        assert system_prompt
        self.user_prompt = user_prompt
        return "Grounded response"


class InMemoryKnowledgePersistenceRepository:
    def __init__(self) -> None:
        self.documents: dict[str, KnowledgeDocumentRecord] = {}
        self.chunks: dict[str, list[PersistedKnowledgeChunk]] = {}
        self.error: Exception | None = None

    def find_document_by_source_url(
        self, source_url: str, *, assistant_id=REDMOOR_ASSISTANT_ID
    ) -> KnowledgeDocumentRecord | None:
        return self.documents.get(source_url)

    @contextmanager
    def transaction(self):
        yield self

    def replace_document(
        self,
        document: KnowledgeDocumentRecord,
        chunks: list[PersistedKnowledgeChunk],
        *,
        ingestion_job_id=None,
        expected_previous_content_hash=None,
        force_replace=False,
    ) -> KnowledgeWriteResult:
        if self.error is not None:
            raise self.error
        existing = self.documents.get(document.source_url)
        previous_count = len(self.chunks.get(document.source_url, []))
        if existing is not None and existing.content_hash == document.content_hash:
            return KnowledgeWriteResult("unchanged", existing.id, previous_count)
        action: Literal["created", "updated"] = "updated" if existing else "created"
        self.documents[document.source_url] = document
        self.chunks[document.source_url] = list(chunks)
        return KnowledgeWriteResult(action, document.id, previous_count)

    def update_document_metadata(self, document: KnowledgeDocumentRecord) -> KnowledgeWriteResult:
        current = self.chunks[document.source_url]
        self.documents[document.source_url] = document
        self.chunks[document.source_url] = [
            replace(item, access_roles=document.access_roles) for item in current
        ]
        return KnowledgeWriteResult("updated", document.id, len(current))

    def lock_ingestion_job(self, ingestion_job_id, document_id):
        raise AssertionError("Synchronous website ingestion does not persist a pipeline job result")

    def find_committed_result(self, ingestion_job_id):
        return None

    def record_committed_result(self, command, result):
        raise AssertionError("Synchronous website ingestion does not persist a pipeline job result")


class FailingWebsiteLoader:
    def load(self, url: str):
        del url
        raise RuntimeError("sensitive upstream failure")


def website_loader(html: str) -> HttpWebsiteLoader:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Type": "text/html; charset=utf-8"},
            content=html.encode(),
            request=request,
        )

    return HttpWebsiteLoader(
        timeout_seconds=2,
        user_agent="ingestion-workflow-test/1.0",
        max_pages=2,
        max_response_size=1024 * 1024,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        resolver=lambda _hostname: PUBLIC_IPS,
    )


def sequenced_website_loader(documents: list[str]) -> HttpWebsiteLoader:
    responses = iter(documents)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Type": "text/html; charset=utf-8"},
            content=next(responses).encode(),
            request=request,
        )

    return HttpWebsiteLoader(
        timeout_seconds=2,
        user_agent="ingestion-workflow-test/1.0",
        max_pages=1,
        max_response_size=1024 * 1024,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        resolver=lambda _hostname: PUBLIC_IPS,
    )


def require_database() -> None:
    required = os.getenv("KNOWLEDGE_PERSISTENCE_POSTGRES_REQUIRED") == "true"
    if not DATABASE_URL:
        if required:
            pytest.fail("DATABASE_URL is required for ingestion workflow PostgreSQL tests")
        pytest.skip("DATABASE_URL is not configured")
    try:
        with psycopg.connect(DATABASE_URL, connect_timeout=2) as connection:
            connection.execute("SELECT 1")
    except psycopg.OperationalError as exc:
        if required:
            pytest.fail(f"Required PostgreSQL test database is unavailable: {exc}")
        pytest.skip(f"PostgreSQL test database is unavailable: {exc}")


def processing_service(*, min_document_length: int = 40) -> ContentProcessingService:
    return ContentProcessingService(
        HtmlContentExtractor(),
        NormalisingTextCleaner(min_document_length=min_document_length),
        SemanticTextChunker(chunk_size=120, overlap=20, min_chunk_size=20),
    )


def persistence_service(
    provider: DeterministicEmbeddingProvider,
    repository: InMemoryKnowledgePersistenceRepository,
) -> KnowledgePersistenceService:
    return KnowledgePersistenceService(
        provider,
        repository,
        assistant_id=REDMOOR_ASSISTANT_ID,
        embedding_dimensions=3,
        embedding_batch_size=100,
    )


@pytest.fixture
def workflow() -> Iterator[
    tuple[
        TestClient,
        InMemoryIngestionJobRepository,
        InMemoryKnowledgePersistenceRepository,
        DeterministicEmbeddingProvider,
    ]
]:
    from main import app

    jobs = InMemoryIngestionJobRepository()
    knowledge = InMemoryKnowledgePersistenceRepository()
    provider = DeterministicEmbeddingProvider()
    html = (FIXTURE_DIR / "business_homepage.html").read_text()
    service = IngestionService(
        jobs,
        website_loader(html),
        processing_service(),
        persistence_service(provider, knowledge),
    )
    app.dependency_overrides[get_ingestion_service] = lambda: service
    yield TestClient(app, raise_server_exceptions=False), jobs, knowledge, provider
    app.dependency_overrides.pop(get_ingestion_service, None)


def test_post_ingestion_loads_processes_persists_and_exposes_retrievable_knowledge(
    workflow, caplog
):
    client, jobs, knowledge, provider = workflow

    with caplog.at_level(logging.INFO):
        response = client.post(
            "/assistant/knowledge/ingestions", json={"url": "https://example.com/knowledge"}
        )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "completed"
    assert body["documentsDiscovered"] == 1
    assert body["documentsProcessed"] == 1
    assert body["chunksCreated"] >= 1
    assert body["error"] is None
    stored_job = jobs.get(UUID(body["jobId"]))
    assert stored_job is not None
    assert stored_job.status.value == "completed"
    assert list(knowledge.documents) == ["https://example.com/knowledge"]
    persisted_chunks = knowledge.chunks["https://example.com/knowledge"]
    assert len(persisted_chunks) == body["chunksCreated"]
    assert provider.batch_calls == [[item.text for item in persisted_chunks]]

    entries = tuple(
        InMemoryVectorEntry(
            record=VectorRecord(
                chunk_id=item.id,
                document_id=item.document_id,
                document_title=knowledge.documents[item_source].title or item_source,
                content=item.text,
                score=0,
                source_uri=item_source,
            ),
            embedding=item.embedding,
        )
        for item_source, chunks in knowledge.chunks.items()
        for item in chunks
    )
    retrieved = RetrievalService(
        provider,
        VectorKnowledgeRepository(InMemoryVectorStore(entries)),
        assistant_id=REDMOOR_ASSISTANT_ID,
        min_score=0.99,
    ).retrieve("What does Northstar Digital do?")

    assert retrieved
    assert any("modernise important services" in chunk.content for chunk in retrieved)
    assert provider.query_calls == ["What does Northstar Digital do?"]
    completion_log = next(
        record for record in caplog.records if record.getMessage() == "Ingestion job completed"
    )
    assert completion_log.website_loading_duration_ms >= 0
    assert completion_log.processing_duration_ms >= 0
    assert completion_log.persistence_duration_ms >= 0
    assert completion_log.total_duration_ms >= 0
    assert "modernise important services" not in caplog.text
    assert "SCRIPT SECRET" not in caplog.text


def test_repeating_unchanged_ingestion_does_not_duplicate_knowledge_or_embeddings(workflow):
    client, _jobs, knowledge, provider = workflow
    request = {"url": "https://example.com/knowledge"}

    first = client.post("/assistant/knowledge/ingestions", json=request)
    initial_chunk_ids = [item.id for item in knowledge.chunks["https://example.com/knowledge"]]
    second = client.post("/assistant/knowledge/ingestions", json=request)

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["status"] == "completed"
    assert second.json()["chunksCreated"] == 0
    assert list(knowledge.documents) == ["https://example.com/knowledge"]
    assert [
        item.id for item in knowledge.chunks["https://example.com/knowledge"]
    ] == initial_chunk_ids
    assert len(provider.batch_calls) == 1


def test_synchronous_ingestion_retries_transient_website_status_once():
    requests = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        if requests == 1:
            return httpx.Response(503, request=request)
        return httpx.Response(
            200,
            headers={"Content-Type": "text/html"},
            content=(FIXTURE_DIR / "business_homepage.html").read_bytes(),
            request=request,
        )

    jobs = InMemoryIngestionJobRepository()
    knowledge = InMemoryKnowledgePersistenceRepository()
    provider = DeterministicEmbeddingProvider()
    loader = HttpWebsiteLoader(
        timeout_seconds=1,
        user_agent="test",
        max_pages=1,
        max_response_size=1024 * 1024,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        resolver=lambda _hostname: PUBLIC_IPS,
    )
    delays: list[float] = []
    service = IngestionService(
        jobs,
        loader,
        processing_service(),
        persistence_service(provider, knowledge),
        classifier=IngestionFailureClassifier(),
        retry_policy=IngestionRetryPolicy(IngestionRetrySettings(2, 0, 1, 0, False)),
        sleeper=delays.append,
    )

    job = service.start_ingestion("https://example.com/knowledge")

    assert job.status.value == "completed"
    assert requests == 2
    assert delays == [0]


def test_synchronous_database_retry_reuses_prepared_embeddings():
    class TransientRepository(InMemoryKnowledgePersistenceRepository):
        def __init__(self):
            super().__init__()
            self.write_attempts = 0

        def replace_document(self, document, chunks, **kwargs):
            self.write_attempts += 1
            if self.write_attempts == 1:
                raise psycopg.OperationalError("temporary database failure")
            return super().replace_document(document, chunks, **kwargs)

    jobs = InMemoryIngestionJobRepository()
    knowledge = TransientRepository()
    provider = DeterministicEmbeddingProvider()
    delays: list[float] = []
    html = (FIXTURE_DIR / "business_homepage.html").read_text()
    service = IngestionService(
        jobs,
        website_loader(html),
        processing_service(),
        persistence_service(provider, knowledge),
        classifier=IngestionFailureClassifier(),
        retry_policy=IngestionRetryPolicy(IngestionRetrySettings(2, 0, 1, 0, False)),
        sleeper=delays.append,
    )

    job = service.start_ingestion("https://example.com/knowledge")

    assert job.status.value == "completed"
    assert knowledge.write_attempts == 2
    assert len(provider.batch_calls) == 1
    assert delays == [0]


def test_database_backed_ingestion_replaces_changed_content_and_supplies_chat_context():
    require_database()

    from main import app

    init_db()
    source_url = f"https://example.com/workflow-{uuid4()}"
    jobs = PostgresIngestionJobRepository()
    provider = DeterministicEmbeddingProvider(EMBEDDING_VECTOR_DIMENSIONS)
    initial_html = (FIXTURE_DIR / "business_homepage.html").read_text()
    changed_html = (FIXTURE_DIR / "service_page.html").read_text()
    service = IngestionService(
        jobs,
        sequenced_website_loader([initial_html, initial_html, changed_html]),
        processing_service(),
        KnowledgePersistenceService(
            provider,
            PostgresKnowledgePersistenceRepository(),
            assistant_id=REDMOOR_ASSISTANT_ID,
            embedding_dimensions=EMBEDDING_VECTOR_DIMENSIONS,
            embedding_batch_size=100,
        ),
    )
    app.dependency_overrides[get_ingestion_service] = lambda: service

    try:
        client = TestClient(app, raise_server_exceptions=False)
        first = client.post("/assistant/knowledge/ingestions", json={"url": source_url})
        second = client.post("/assistant/knowledge/ingestions", json={"url": source_url})
        changed = client.post("/assistant/knowledge/ingestions", json={"url": source_url})

        assert first.status_code == 201
        assert first.json()["status"] == "completed"
        assert first.json()["chunksCreated"] >= 1
        assert second.status_code == 201
        assert second.json()["status"] == "completed"
        assert second.json()["chunksCreated"] == 0
        assert changed.status_code == 201
        assert changed.json()["status"] == "completed"
        assert changed.json()["chunksCreated"] >= 1
        for body in (first.json(), second.json(), changed.json()):
            stored_job = jobs.get(UUID(body["jobId"]))
            assert stored_job is not None
            assert stored_job.status.value == "completed"
        assert len(provider.batch_calls) == 2
        assert any("grounded assistants" in text for text in provider.batch_calls[1])

        with get_connection() as connection:
            document_count, chunk_count = connection.execute(
                """
                SELECT count(DISTINCT documents.id), count(chunks.id)
                FROM documents JOIN chunks ON chunks.doc_id = documents.id
                WHERE documents.source_url = %s
                """,
                (source_url,),
            ).fetchone()
        assert document_count == 1
        assert chunk_count == changed.json()["chunksCreated"]

        retrieval = RetrievalService(
            provider,
            VectorKnowledgeRepository(PgVectorStore()),
            assistant_id=REDMOOR_ASSISTANT_ID,
            limit=1000,
            min_score=0.99,
        )
        retrieved = retrieval.retrieve("What does Northstar Digital build?")
        matching = [chunk for chunk in retrieved if chunk.document.source_uri == source_url]
        assert matching
        assert any("grounded assistants" in chunk.content for chunk in matching)
        assert all("modernise important services" not in chunk.content for chunk in matching)
        assert {chunk.document.title for chunk in matching} == {
            "AI Integration | Northstar Digital"
        }

        completion_provider = RecordingCompletionProvider()
        chat_response = ChatService(completion_provider, retrieval).chat(
            ChatRequest(message="What does Northstar Digital build?")
        )

        assert completion_provider.user_prompt is not None
        assert "grounded assistants" in completion_provider.user_prompt
        assert "modernise important services" not in completion_provider.user_prompt
        assert chat_response.message == "Grounded response"
        source_titles = [source.title for source in chat_response.sources]
        assert "AI Integration | Northstar Digital" in source_titles
        assert "Northstar Digital" not in source_titles
    finally:
        app.dependency_overrides.pop(get_ingestion_service, None)
        with get_connection() as connection:
            connection.execute("DELETE FROM ingestion_jobs WHERE source_url = %s", (source_url,))
            connection.execute("DELETE FROM documents WHERE source_url = %s", (source_url,))


@pytest.mark.parametrize(
    ("stage", "expected_error"),
    [
        ("loading", "Website loading failed."),
        ("processing", "Content processing failed."),
        ("persistence", "Knowledge persistence failed."),
    ],
)
def test_stage_failure_persists_failed_job_and_returns_only_a_safe_error(stage, expected_error):
    from main import app

    jobs = InMemoryIngestionJobRepository()
    knowledge = InMemoryKnowledgePersistenceRepository()
    provider = DeterministicEmbeddingProvider()
    useful_html = (FIXTURE_DIR / "business_homepage.html").read_text()
    low_value_html = (FIXTURE_DIR / "low_value.html").read_text()
    loader = (
        FailingWebsiteLoader()
        if stage == "loading"
        else website_loader(low_value_html if stage == "processing" else useful_html)
    )
    if stage == "persistence":
        knowledge.error = RuntimeError("sensitive database failure")
    service = IngestionService(
        jobs,
        loader,
        processing_service(),
        persistence_service(provider, knowledge),
    )
    app.dependency_overrides[get_ingestion_service] = lambda: service

    try:
        response = TestClient(app, raise_server_exceptions=False).post(
            "/assistant/knowledge/ingestions",
            json={"url": "https://example.com/knowledge"},
        )
    finally:
        app.dependency_overrides.pop(get_ingestion_service, None)

    assert response.status_code == 500
    assert response.json() == {"detail": "Knowledge ingestion failed."}
    stored = jobs.latest()
    assert stored is not None
    assert stored.status.value == "failed"
    assert stored.error_message == expected_error
    assert stored.started_at is not None
    assert stored.completed_at is not None
    assert "sensitive" not in response.text
    assert knowledge.documents == {}
