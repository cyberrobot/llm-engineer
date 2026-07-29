import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

CHUNKS_SEARCH_RESULTS_LIMIT = 8
CHUNK_TOP_K = 3
CHUNKS_MAX_DISTANCE = 0.8
WEIGHT_KEYWORD_MATCH = 0.2
WEIGHT_EMBEDDING_SIMILARITY = 0.8
AUDIT_LOG_LIMIT = 10
EMBEDDING_VECTOR_DIMENSIONS = 1536

DATABASE_URL = os.getenv("DATABASE_URL")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
DISABLE_RATE_LIMITS = os.getenv("DISABLE_RATE_LIMITS", "false").lower() == "true"
DISABLE_INGEST = os.getenv("DISABLE_INGEST", "false").lower() == "true"
DISABLE_CACHE = os.getenv("DISABLE_CACHE", "false").lower() == "true"
DISABLE_AUDIT_LOGS = os.getenv("DISABLE_AUDIT_LOGS", "false").lower() == "true"
DEBUG_DELAY = os.getenv("DEBUG_DELAY", "false").lower() == "true"


@dataclass(frozen=True)
class AISettings:
    """Environment-backed configuration for the Assistant AI provider."""

    provider: str
    openai_api_key: str | None
    openai_model: str
    request_timeout: float
    embedding_model: str = "text-embedding-3-small"


@dataclass(frozen=True)
class KnowledgePersistenceSettings:
    """Canonical vector schema and provider batching limits."""

    embedding_dimensions: int
    embedding_batch_size: int


@dataclass(frozen=True)
class WebsiteLoaderSettings:
    """Environment-backed limits for raw website retrieval."""

    timeout_seconds: float
    max_pages: int
    user_agent: str
    max_response_size: int


@dataclass(frozen=True)
class ContentProcessingSettings:
    """Character-based limits for deterministic website content processing."""

    chunk_size_characters: int
    chunk_overlap_characters: int
    min_chunk_size_characters: int
    min_document_length_characters: int


def get_ai_settings() -> AISettings:
    """Read AI configuration from the environment at the composition boundary."""
    timeout = float(os.getenv("AI_REQUEST_TIMEOUT", "30"))
    if timeout <= 0:
        raise ValueError("AI_REQUEST_TIMEOUT must be greater than zero")

    return AISettings(
        provider=os.getenv("AI_PROVIDER", "openai").strip().lower(),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-5.5").strip(),
        request_timeout=timeout,
        embedding_model=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small").strip(),
    )


def get_knowledge_persistence_settings() -> KnowledgePersistenceSettings:
    batch_size = int(os.getenv("EMBEDDING_BATCH_SIZE", "100"))
    if batch_size <= 0:
        raise ValueError("EMBEDDING_BATCH_SIZE must be greater than zero")
    return KnowledgePersistenceSettings(
        embedding_dimensions=EMBEDDING_VECTOR_DIMENSIONS,
        embedding_batch_size=batch_size,
    )


def get_website_loader_settings() -> WebsiteLoaderSettings:
    timeout_seconds = float(os.getenv("INGESTION_TIMEOUT_SECONDS", "10"))
    max_pages = int(os.getenv("INGESTION_MAX_PAGES", "25"))
    user_agent = os.getenv("INGESTION_USER_AGENT", "AI-Discovery-Assistant/1.0").strip()
    max_response_size = int(os.getenv("INGESTION_MAX_RESPONSE_SIZE", str(5 * 1024 * 1024)))

    if timeout_seconds <= 0:
        raise ValueError("INGESTION_TIMEOUT_SECONDS must be greater than zero")
    if max_pages <= 0:
        raise ValueError("INGESTION_MAX_PAGES must be greater than zero")
    if not user_agent:
        raise ValueError("INGESTION_USER_AGENT must not be empty")
    if max_response_size <= 0:
        raise ValueError("INGESTION_MAX_RESPONSE_SIZE must be greater than zero")
    return WebsiteLoaderSettings(
        timeout_seconds=timeout_seconds,
        max_pages=max_pages,
        user_agent=user_agent,
        max_response_size=max_response_size,
    )


def get_content_processing_settings() -> ContentProcessingSettings:
    chunk_size = int(os.getenv("INGESTION_CHUNK_SIZE_CHARACTERS", "1200"))
    overlap = int(os.getenv("INGESTION_CHUNK_OVERLAP_CHARACTERS", "150"))
    min_chunk_size = int(os.getenv("INGESTION_MIN_CHUNK_SIZE_CHARACTERS", "100"))
    min_document_length = int(os.getenv("INGESTION_MIN_DOCUMENT_LENGTH_CHARACTERS", "50"))

    if chunk_size <= 0:
        raise ValueError("INGESTION_CHUNK_SIZE_CHARACTERS must be greater than zero")
    if overlap < 0:
        raise ValueError("INGESTION_CHUNK_OVERLAP_CHARACTERS must not be negative")
    if overlap >= chunk_size:
        raise ValueError(
            "INGESTION_CHUNK_OVERLAP_CHARACTERS must be smaller than "
            "INGESTION_CHUNK_SIZE_CHARACTERS"
        )
    if min_chunk_size <= 0:
        raise ValueError("INGESTION_MIN_CHUNK_SIZE_CHARACTERS must be greater than zero")
    if min_chunk_size > chunk_size:
        raise ValueError(
            "INGESTION_MIN_CHUNK_SIZE_CHARACTERS must not exceed INGESTION_CHUNK_SIZE_CHARACTERS"
        )
    if min_document_length < 0:
        raise ValueError("INGESTION_MIN_DOCUMENT_LENGTH_CHARACTERS must not be negative")
    return ContentProcessingSettings(
        chunk_size_characters=chunk_size,
        chunk_overlap_characters=overlap,
        min_chunk_size_characters=min_chunk_size,
        min_document_length_characters=min_document_length,
    )


def get_openai_api_key() -> str | None:
    return os.getenv("OPENAI_API_KEY")


def get_ingest_api_key() -> str | None:
    return os.getenv("INGEST_API_KEY") or os.getenv("ADMIN_API_KEY")


def get_max_upload_bytes() -> int:
    return int(os.getenv("MAX_UPLOAD_MB", "25")) * 1024 * 1024


def get_upload_dir() -> Path:
    return Path(os.getenv("UPLOAD_DIR", "uploads"))
