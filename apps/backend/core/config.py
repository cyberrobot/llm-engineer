import os
import socket
from dataclasses import dataclass
from ipaddress import ip_network
from pathlib import Path
from typing import ClassVar, Literal, cast
from urllib.parse import urlsplit
from uuid import uuid4

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


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalised = value.strip().lower()
    if normalised == "true":
        return True
    if normalised == "false":
        return False
    raise ValueError(f"{name} must be true or false")


@dataclass(frozen=True)
class AISettings:
    """Environment-backed configuration for the Assistant AI provider."""

    provider: str
    openai_api_key: str | None
    openai_model: str
    request_timeout: float
    embedding_model: str = "text-embedding-3-small"
    max_retries: int = 2


@dataclass(frozen=True)
class PublicAssistantChatSettings:
    """Validated server-owned functional and resource-protection policy."""

    enabled: bool
    retrieval_limit: int
    minimum_similarity_score: float
    maximum_output_tokens: int
    temperature: float
    allowed_origins: tuple[str, ...]
    trusted_proxy_networks: tuple[str, ...]
    client_key_hash_secret: str
    maximum_message_characters: int
    maximum_history_message_characters: int
    maximum_history_messages: int
    maximum_history_characters: int
    maximum_history_tokens: int
    maximum_request_bytes: int
    maximum_input_tokens: int
    maximum_context_chunks: int
    maximum_context_tokens: int
    model_context_tokens: int
    maximum_estimated_cost_usd: float
    rate_limit_per_minute: int
    rate_limit_per_hour: int
    global_rate_limit_per_minute: int
    maximum_concurrent_requests_per_client: int
    maximum_concurrent_requests_global: int
    request_timeout_seconds: float
    first_token_timeout_seconds: float

    _MODEL_INPUT_USD_PER_MILLION: ClassVar[dict[str, float]] = {
        "gpt-5.5": 5.0,
        "gpt-5.5-2026-04-23": 5.0,
    }
    _MODEL_OUTPUT_USD_PER_MILLION: ClassVar[dict[str, float]] = {
        "gpt-5.5": 30.0,
        "gpt-5.5-2026-04-23": 30.0,
    }
    _MODEL_CONTEXT_TOKENS: ClassVar[dict[str, int]] = {
        "gpt-5.5": 1_050_000,
        "gpt-5.5-2026-04-23": 1_050_000,
    }

    def __post_init__(self) -> None:
        if not self.client_key_hash_secret.strip():
            raise ValueError("PUBLIC_CHAT_CLIENT_KEY_HASH_SECRET must not be empty")
        if self.retrieval_limit < 1:
            raise ValueError("PUBLIC_CHAT_RETRIEVAL_LIMIT must be at least 1")
        if not -1 <= self.minimum_similarity_score <= 1:
            raise ValueError("PUBLIC_CHAT_MIN_SIMILARITY_SCORE must be between -1 and 1")
        if self.maximum_output_tokens < 1:
            raise ValueError("PUBLIC_CHAT_MAX_OUTPUT_TOKENS must be at least 1")
        if not 0 <= self.temperature <= 2:
            raise ValueError("PUBLIC_CHAT_TEMPERATURE must be between 0 and 2")
        for origin in self.allowed_origins:
            if origin == "*":
                raise ValueError("PUBLIC_CHAT_ALLOWED_ORIGINS must not contain a wildcard")
            parsed = urlsplit(origin)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.netloc
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError("PUBLIC_CHAT_ALLOWED_ORIGINS must contain exact HTTP(S) origins")
        for network in self.trusted_proxy_networks:
            try:
                ip_network(network, strict=False)
            except ValueError as exc:
                raise ValueError("PUBLIC_CHAT_TRUSTED_PROXIES must contain IP networks") from exc
        for name, value in (
            ("PUBLIC_CHAT_MAX_MESSAGE_CHARACTERS", self.maximum_message_characters),
            (
                "PUBLIC_CHAT_MAX_HISTORY_MESSAGE_CHARACTERS",
                self.maximum_history_message_characters,
            ),
            ("PUBLIC_CHAT_MAX_HISTORY_MESSAGES", self.maximum_history_messages),
            ("PUBLIC_CHAT_MAX_HISTORY_CHARACTERS", self.maximum_history_characters),
            ("PUBLIC_CHAT_MAX_HISTORY_TOKENS", self.maximum_history_tokens),
            ("PUBLIC_CHAT_MAX_REQUEST_BYTES", self.maximum_request_bytes),
            ("PUBLIC_CHAT_MAX_INPUT_TOKENS", self.maximum_input_tokens),
            ("PUBLIC_CHAT_MAX_CONTEXT_CHUNKS", self.maximum_context_chunks),
            ("PUBLIC_CHAT_MAX_CONTEXT_TOKENS", self.maximum_context_tokens),
            ("PUBLIC_CHAT_MODEL_CONTEXT_TOKENS", self.model_context_tokens),
            ("PUBLIC_CHAT_RATE_LIMIT_PER_MINUTE", self.rate_limit_per_minute),
            ("PUBLIC_CHAT_RATE_LIMIT_PER_HOUR", self.rate_limit_per_hour),
            ("PUBLIC_CHAT_GLOBAL_RATE_LIMIT_PER_MINUTE", self.global_rate_limit_per_minute),
            (
                "PUBLIC_CHAT_MAX_CONCURRENT_REQUESTS_PER_CLIENT",
                self.maximum_concurrent_requests_per_client,
            ),
            (
                "PUBLIC_CHAT_MAX_CONCURRENT_REQUESTS_GLOBAL",
                self.maximum_concurrent_requests_global,
            ),
        ):
            if value < 1:
                raise ValueError(f"{name} must be at least 1")
        if self.maximum_history_messages % 2:
            raise ValueError("PUBLIC_CHAT_MAX_HISTORY_MESSAGES must be even")
        if self.maximum_context_chunks > self.retrieval_limit:
            raise ValueError(
                "PUBLIC_CHAT_MAX_CONTEXT_CHUNKS must not exceed PUBLIC_CHAT_RETRIEVAL_LIMIT"
            )
        if self.maximum_input_tokens + self.maximum_output_tokens > self.model_context_tokens:
            raise ValueError("Public chat input and output budgets exceed the model context window")
        if self.request_timeout_seconds <= 0 or self.first_token_timeout_seconds <= 0:
            raise ValueError("Public chat timeouts must be greater than zero")
        if self.first_token_timeout_seconds > self.request_timeout_seconds:
            raise ValueError(
                "PUBLIC_CHAT_MODEL_FIRST_TOKEN_TIMEOUT_SECONDS must not exceed the request timeout"
            )
        if self.maximum_estimated_cost_usd <= 0:
            raise ValueError("PUBLIC_CHAT_MAX_ESTIMATED_COST must be greater than zero")
        if self.enabled:
            model = get_ai_settings().openai_model
            if model not in self._MODEL_CONTEXT_TOKENS:
                raise ValueError(f"OPENAI_MODEL {model!r} is not approved for public chat")
            if self.model_context_tokens > self._MODEL_CONTEXT_TOKENS[model]:
                raise ValueError("PUBLIC_CHAT_MODEL_CONTEXT_TOKENS exceeds approved model metadata")
            maximum_cost = (
                self.maximum_input_tokens * self._MODEL_INPUT_USD_PER_MILLION[model]
                + self.maximum_output_tokens * self._MODEL_OUTPUT_USD_PER_MILLION[model]
            ) / 1_000_000
            if maximum_cost > self.maximum_estimated_cost_usd:
                raise ValueError(
                    "Public chat maximum estimated cost exceeds the configured cost cap"
                )

    @classmethod
    def development_defaults(cls, *, enabled: bool = False) -> "PublicAssistantChatSettings":
        return cls(
            enabled=enabled,
            retrieval_limit=3,
            minimum_similarity_score=0.7,
            maximum_output_tokens=500,
            temperature=0.2,
            allowed_origins=("http://localhost:5173",),
            trusted_proxy_networks=(),
            client_key_hash_secret="development-only-public-chat-key",
            maximum_message_characters=4_000,
            maximum_history_message_characters=4_000,
            maximum_history_messages=12,
            maximum_history_characters=12_000,
            maximum_history_tokens=12_000,
            maximum_request_bytes=32_768,
            maximum_input_tokens=8_000,
            maximum_context_chunks=3,
            maximum_context_tokens=4_000,
            model_context_tokens=1_050_000,
            maximum_estimated_cost_usd=0.10,
            rate_limit_per_minute=10,
            rate_limit_per_hour=100,
            global_rate_limit_per_minute=300,
            maximum_concurrent_requests_per_client=2,
            maximum_concurrent_requests_global=20,
            request_timeout_seconds=45,
            first_token_timeout_seconds=15,
        )

    @staticmethod
    def production_environment_names() -> tuple[str, ...]:
        return (
            "PUBLIC_CHAT_ALLOWED_ORIGINS",
            "PUBLIC_CHAT_TRUSTED_PROXIES",
            "FORWARDED_ALLOW_IPS",
            "PUBLIC_CHAT_CLIENT_KEY_HASH_SECRET",
            "PUBLIC_CHAT_MAX_MESSAGE_CHARACTERS",
            "PUBLIC_CHAT_MAX_HISTORY_MESSAGE_CHARACTERS",
            "PUBLIC_CHAT_MAX_HISTORY_MESSAGES",
            "PUBLIC_CHAT_MAX_HISTORY_CHARACTERS",
            "PUBLIC_CHAT_MAX_HISTORY_TOKENS",
            "PUBLIC_CHAT_MAX_REQUEST_BYTES",
            "PUBLIC_CHAT_MAX_INPUT_TOKENS",
            "PUBLIC_CHAT_MAX_CONTEXT_CHUNKS",
            "PUBLIC_CHAT_MAX_CONTEXT_TOKENS",
            "PUBLIC_CHAT_MODEL_CONTEXT_TOKENS",
            "PUBLIC_CHAT_MAX_OUTPUT_TOKENS",
            "PUBLIC_CHAT_MAX_ESTIMATED_COST",
            "PUBLIC_CHAT_RATE_LIMIT_PER_MINUTE",
            "PUBLIC_CHAT_RATE_LIMIT_PER_HOUR",
            "PUBLIC_CHAT_GLOBAL_RATE_LIMIT_PER_MINUTE",
            "PUBLIC_CHAT_MAX_CONCURRENT_REQUESTS_PER_CLIENT",
            "PUBLIC_CHAT_MAX_CONCURRENT_REQUESTS_GLOBAL",
            "PUBLIC_CHAT_REQUEST_TIMEOUT_SECONDS",
            "PUBLIC_CHAT_MODEL_FIRST_TOKEN_TIMEOUT_SECONDS",
            "REDIS_URL",
        )


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
    max_retries: int = 2


@dataclass(frozen=True)
class DatabaseSettings:
    """Bounded database connection and statement execution settings."""

    connect_timeout_seconds: int
    operation_timeout_seconds: float


@dataclass(frozen=True)
class HealthCheckSettings:
    """Short timeout and dependency enablement for repeatable operational probes."""

    timeout_seconds: float
    redis_disabled: bool


@dataclass(frozen=True)
class ContentProcessingSettings:
    """Character-based limits for deterministic website content processing."""

    chunk_size_characters: int
    chunk_overlap_characters: int
    min_chunk_size_characters: int
    min_document_length_characters: int


@dataclass(frozen=True)
class IngestionRetrySettings:
    """Synchronous per-step retry limits; maximum_attempts includes attempt one."""

    maximum_attempts: int
    initial_delay_seconds: float
    backoff_multiplier: float
    maximum_delay_seconds: float
    jitter_enabled: bool

    def __post_init__(self) -> None:
        if self.maximum_attempts < 1:
            raise ValueError("INGESTION_RETRY_MAX_ATTEMPTS must be at least 1")
        if self.initial_delay_seconds < 0:
            raise ValueError("INGESTION_RETRY_INITIAL_DELAY_SECONDS must not be negative")
        if self.backoff_multiplier < 1:
            raise ValueError("INGESTION_RETRY_BACKOFF_MULTIPLIER must be at least 1")
        if self.maximum_delay_seconds < 0:
            raise ValueError("INGESTION_RETRY_MAX_DELAY_SECONDS must not be negative")
        if self.maximum_delay_seconds < self.initial_delay_seconds:
            raise ValueError(
                "INGESTION_RETRY_MAX_DELAY_SECONDS must not be smaller than "
                "INGESTION_RETRY_INITIAL_DELAY_SECONDS"
            )


@dataclass(frozen=True)
class IngestionWorkerSettings:
    enabled: bool
    poll_interval_seconds: float
    lease_seconds: float
    heartbeat_interval_seconds: float
    concurrency: int
    shutdown_grace_seconds: float
    worker_id: str

    def __post_init__(self) -> None:
        if self.poll_interval_seconds <= 0:
            raise ValueError("INGESTION_WORKER_POLL_INTERVAL_SECONDS must be greater than zero")
        if self.lease_seconds <= 0:
            raise ValueError("INGESTION_WORKER_LEASE_SECONDS must be greater than zero")
        if self.heartbeat_interval_seconds <= 0:
            raise ValueError(
                "INGESTION_WORKER_HEARTBEAT_INTERVAL_SECONDS must be greater than zero"
            )
        if self.heartbeat_interval_seconds >= self.lease_seconds:
            raise ValueError(
                "INGESTION_WORKER_HEARTBEAT_INTERVAL_SECONDS must be shorter than "
                "INGESTION_WORKER_LEASE_SECONDS"
            )
        if self.concurrency < 1:
            raise ValueError("INGESTION_WORKER_CONCURRENCY must be at least 1")
        if self.shutdown_grace_seconds < 0:
            raise ValueError("INGESTION_WORKER_SHUTDOWN_GRACE_SECONDS must not be negative")
        if not self.worker_id.strip():
            raise ValueError("INGESTION_WORKER_ID must not be empty")


@dataclass(frozen=True)
class AdminAuthenticationSettings:
    """Central security policy for administrator credentials and sessions."""

    bootstrap_email: str | None
    bootstrap_password: str | None
    session_ttl_seconds: int
    cookie_name: str
    cookie_secure: bool
    cookie_samesite: Literal["lax", "strict"]
    trusted_origins: tuple[str, ...]
    login_max_failures: int
    login_lockout_seconds: int
    throttle_window_seconds: int
    throttle_ip_attempts: int
    throttle_email_attempts: int
    throttle_global_attempts: int

    def __post_init__(self) -> None:
        if (self.bootstrap_email is None) != (self.bootstrap_password is None):
            raise ValueError(
                "ADMIN_BOOTSTRAP_EMAIL and ADMIN_BOOTSTRAP_PASSWORD must be configured together"
            )
        if self.session_ttl_seconds <= 0:
            raise ValueError("ADMIN_SESSION_TTL_SECONDS must be greater than zero")
        if not self.cookie_name.strip():
            raise ValueError("ADMIN_SESSION_COOKIE_NAME must not be empty")
        if self.cookie_samesite not in {"lax", "strict"}:
            raise ValueError("ADMIN_SESSION_COOKIE_SAMESITE must be lax or strict")
        if not self.trusted_origins:
            raise ValueError("ADMIN_TRUSTED_ORIGINS must include at least one origin")
        if any(not origin.startswith(("http://", "https://")) for origin in self.trusted_origins):
            raise ValueError("ADMIN_TRUSTED_ORIGINS must contain absolute HTTP(S) origins")
        for name, value in (
            ("ADMIN_LOGIN_MAX_FAILURES", self.login_max_failures),
            ("ADMIN_LOGIN_LOCKOUT_SECONDS", self.login_lockout_seconds),
            ("ADMIN_LOGIN_THROTTLE_WINDOW_SECONDS", self.throttle_window_seconds),
            ("ADMIN_LOGIN_THROTTLE_IP_ATTEMPTS", self.throttle_ip_attempts),
            ("ADMIN_LOGIN_THROTTLE_EMAIL_ATTEMPTS", self.throttle_email_attempts),
            ("ADMIN_LOGIN_THROTTLE_GLOBAL_ATTEMPTS", self.throttle_global_attempts),
        ):
            if value <= 0:
                raise ValueError(f"{name} must be greater than zero")


def get_ai_settings() -> AISettings:
    """Read AI configuration from the environment at the composition boundary."""
    timeout = _env_float("AI_REQUEST_TIMEOUT", 30)
    max_retries = _env_int("AI_MAX_RETRIES", 2)
    if timeout <= 0:
        raise ValueError("AI_REQUEST_TIMEOUT must be greater than zero")
    if max_retries < 0:
        raise ValueError("AI_MAX_RETRIES must not be negative")

    return AISettings(
        provider=os.getenv("AI_PROVIDER", "openai").strip().lower(),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-5.5").strip(),
        request_timeout=timeout,
        embedding_model=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small").strip(),
        max_retries=max_retries,
    )


def get_public_assistant_chat_settings() -> PublicAssistantChatSettings:
    defaults = PublicAssistantChatSettings.development_defaults()
    enabled = _env_bool("PUBLIC_ASSISTANT_CHAT_ENABLED", False)
    environment = os.getenv("APP_ENV", "development").strip().lower()
    if enabled and environment == "production":
        missing = [
            name
            for name in PublicAssistantChatSettings.production_environment_names()
            if not os.getenv(name, "").strip()
        ]
        if missing:
            raise ValueError(f"{missing[0]} is required when public chat is enabled in production")
        if _env_bool("DISABLE_RATE_LIMITS", False):
            raise ValueError("DISABLE_RATE_LIMITS must be false for production public chat")
    origins = tuple(
        item.strip()
        for item in os.getenv(
            "PUBLIC_CHAT_ALLOWED_ORIGINS", ",".join(defaults.allowed_origins)
        ).split(",")
        if item.strip()
    )
    proxies = tuple(
        item.strip()
        for item in os.getenv("PUBLIC_CHAT_TRUSTED_PROXIES", "").split(",")
        if item.strip()
    )
    if enabled and environment == "production":
        uvicorn_proxies = tuple(
            item.strip() for item in os.getenv("FORWARDED_ALLOW_IPS", "").split(",") if item.strip()
        )
        if proxies != uvicorn_proxies:
            raise ValueError("FORWARDED_ALLOW_IPS must exactly match PUBLIC_CHAT_TRUSTED_PROXIES")
        if not origins:
            raise ValueError("PUBLIC_CHAT_ALLOWED_ORIGINS must not be empty")
        if len(os.getenv("PUBLIC_CHAT_CLIENT_KEY_HASH_SECRET", "")) < 32:
            raise ValueError(
                "PUBLIC_CHAT_CLIENT_KEY_HASH_SECRET must contain at least 32 characters"
            )
    return PublicAssistantChatSettings(
        enabled=enabled,
        retrieval_limit=_env_int("PUBLIC_CHAT_RETRIEVAL_LIMIT", 3),
        minimum_similarity_score=_env_float("PUBLIC_CHAT_MIN_SIMILARITY_SCORE", 0.7),
        maximum_output_tokens=_env_int("PUBLIC_CHAT_MAX_OUTPUT_TOKENS", 500),
        temperature=_env_float("PUBLIC_CHAT_TEMPERATURE", 0.2),
        allowed_origins=origins,
        trusted_proxy_networks=proxies,
        client_key_hash_secret=os.getenv(
            "PUBLIC_CHAT_CLIENT_KEY_HASH_SECRET", defaults.client_key_hash_secret
        ),
        maximum_message_characters=_env_int("PUBLIC_CHAT_MAX_MESSAGE_CHARACTERS", 4_000),
        maximum_history_message_characters=_env_int(
            "PUBLIC_CHAT_MAX_HISTORY_MESSAGE_CHARACTERS", 4_000
        ),
        maximum_history_messages=_env_int("PUBLIC_CHAT_MAX_HISTORY_MESSAGES", 12),
        maximum_history_characters=_env_int("PUBLIC_CHAT_MAX_HISTORY_CHARACTERS", 12_000),
        maximum_history_tokens=_env_int("PUBLIC_CHAT_MAX_HISTORY_TOKENS", 12_000),
        maximum_request_bytes=_env_int("PUBLIC_CHAT_MAX_REQUEST_BYTES", 32_768),
        maximum_input_tokens=_env_int("PUBLIC_CHAT_MAX_INPUT_TOKENS", 8_000),
        maximum_context_chunks=_env_int("PUBLIC_CHAT_MAX_CONTEXT_CHUNKS", 3),
        maximum_context_tokens=_env_int("PUBLIC_CHAT_MAX_CONTEXT_TOKENS", 4_000),
        model_context_tokens=_env_int("PUBLIC_CHAT_MODEL_CONTEXT_TOKENS", 1_050_000),
        maximum_estimated_cost_usd=_env_float("PUBLIC_CHAT_MAX_ESTIMATED_COST", 0.10),
        rate_limit_per_minute=_env_int("PUBLIC_CHAT_RATE_LIMIT_PER_MINUTE", 10),
        rate_limit_per_hour=_env_int("PUBLIC_CHAT_RATE_LIMIT_PER_HOUR", 100),
        global_rate_limit_per_minute=_env_int("PUBLIC_CHAT_GLOBAL_RATE_LIMIT_PER_MINUTE", 300),
        maximum_concurrent_requests_per_client=_env_int(
            "PUBLIC_CHAT_MAX_CONCURRENT_REQUESTS_PER_CLIENT", 2
        ),
        maximum_concurrent_requests_global=_env_int(
            "PUBLIC_CHAT_MAX_CONCURRENT_REQUESTS_GLOBAL", 20
        ),
        request_timeout_seconds=_env_float("PUBLIC_CHAT_REQUEST_TIMEOUT_SECONDS", 45),
        first_token_timeout_seconds=_env_float("PUBLIC_CHAT_MODEL_FIRST_TOKEN_TIMEOUT_SECONDS", 15),
    )


def get_knowledge_persistence_settings() -> KnowledgePersistenceSettings:
    batch_size = _env_int("EMBEDDING_BATCH_SIZE", 100)
    if batch_size <= 0:
        raise ValueError("EMBEDDING_BATCH_SIZE must be greater than zero")
    return KnowledgePersistenceSettings(
        embedding_dimensions=EMBEDDING_VECTOR_DIMENSIONS,
        embedding_batch_size=batch_size,
    )


def get_website_loader_settings() -> WebsiteLoaderSettings:
    timeout_seconds = _env_float("INGESTION_TIMEOUT_SECONDS", 10)
    max_pages = _env_int("INGESTION_MAX_PAGES", 25)
    user_agent = os.getenv("INGESTION_USER_AGENT", "AI-Discovery-Assistant/1.0").strip()
    max_response_size = _env_int("INGESTION_MAX_RESPONSE_SIZE", 5 * 1024 * 1024)
    max_retries = _env_int("INGESTION_HTTP_RETRIES", 2)

    if timeout_seconds <= 0:
        raise ValueError("INGESTION_TIMEOUT_SECONDS must be greater than zero")
    if max_pages <= 0:
        raise ValueError("INGESTION_MAX_PAGES must be greater than zero")
    if not user_agent:
        raise ValueError("INGESTION_USER_AGENT must not be empty")
    if max_response_size <= 0:
        raise ValueError("INGESTION_MAX_RESPONSE_SIZE must be greater than zero")
    if max_retries < 0:
        raise ValueError("INGESTION_HTTP_RETRIES must not be negative")
    return WebsiteLoaderSettings(
        timeout_seconds=timeout_seconds,
        max_pages=max_pages,
        user_agent=user_agent,
        max_response_size=max_response_size,
        max_retries=max_retries,
    )


def get_database_settings() -> DatabaseSettings:
    connect_timeout = _env_int("DATABASE_CONNECT_TIMEOUT_SECONDS", 5)
    operation_timeout = _env_float("DATABASE_OPERATION_TIMEOUT_SECONDS", 30)
    if connect_timeout <= 0:
        raise ValueError("DATABASE_CONNECT_TIMEOUT_SECONDS must be greater than zero")
    if operation_timeout <= 0:
        raise ValueError("DATABASE_OPERATION_TIMEOUT_SECONDS must be greater than zero")
    return DatabaseSettings(
        connect_timeout_seconds=connect_timeout,
        operation_timeout_seconds=operation_timeout,
    )


def get_health_check_settings() -> HealthCheckSettings:
    timeout_seconds = _env_float("HEALTH_CHECK_TIMEOUT_SECONDS", 2)
    if timeout_seconds <= 0 or timeout_seconds > 10:
        raise ValueError("HEALTH_CHECK_TIMEOUT_SECONDS must be greater than zero and at most 10")
    return HealthCheckSettings(
        timeout_seconds=timeout_seconds,
        redis_disabled=_env_bool("DISABLE_CACHE", False),
    )


def get_content_processing_settings() -> ContentProcessingSettings:
    chunk_size = _env_int("INGESTION_CHUNK_SIZE_CHARACTERS", 1200)
    overlap = _env_int("INGESTION_CHUNK_OVERLAP_CHARACTERS", 150)
    min_chunk_size = _env_int("INGESTION_MIN_CHUNK_SIZE_CHARACTERS", 100)
    min_document_length = _env_int("INGESTION_MIN_DOCUMENT_LENGTH_CHARACTERS", 50)

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


def get_ingestion_retry_settings() -> IngestionRetrySettings:
    return IngestionRetrySettings(
        maximum_attempts=_env_int("INGESTION_RETRY_MAX_ATTEMPTS", 3),
        initial_delay_seconds=_env_float("INGESTION_RETRY_INITIAL_DELAY_SECONDS", 1),
        backoff_multiplier=_env_float("INGESTION_RETRY_BACKOFF_MULTIPLIER", 2),
        maximum_delay_seconds=_env_float("INGESTION_RETRY_MAX_DELAY_SECONDS", 30),
        jitter_enabled=_env_bool("INGESTION_RETRY_JITTER_ENABLED", True),
    )


def get_ingestion_worker_settings() -> IngestionWorkerSettings:
    configured_id = os.getenv("INGESTION_WORKER_ID")
    worker_id = (
        configured_id.strip()
        if configured_id is not None
        else f"{socket.gethostname()}-{os.getpid()}-{uuid4().hex[:12]}"
    )
    return IngestionWorkerSettings(
        enabled=_env_bool("INGESTION_WORKER_ENABLED", True),
        poll_interval_seconds=_env_float("INGESTION_WORKER_POLL_INTERVAL_SECONDS", 1),
        lease_seconds=_env_float("INGESTION_WORKER_LEASE_SECONDS", 60),
        heartbeat_interval_seconds=_env_float("INGESTION_WORKER_HEARTBEAT_INTERVAL_SECONDS", 20),
        concurrency=_env_int("INGESTION_WORKER_CONCURRENCY", 1),
        shutdown_grace_seconds=_env_float("INGESTION_WORKER_SHUTDOWN_GRACE_SECONDS", 30),
        worker_id=worker_id,
    )


def get_openai_api_key() -> str | None:
    return os.getenv("OPENAI_API_KEY")


def get_ingest_api_key() -> str | None:
    return os.getenv("INGEST_API_KEY") or os.getenv("ADMIN_API_KEY")


def get_admin_api_key() -> str | None:
    """Return the administrative API credential, if administration is configured."""

    value = os.getenv("ADMIN_API_KEY")
    return value if value and value.strip() else None


def get_admin_authentication_settings() -> AdminAuthenticationSettings:
    environment = os.getenv("APP_ENV", "development").strip().lower()
    email = os.getenv("ADMIN_BOOTSTRAP_EMAIL")
    password = os.getenv("ADMIN_BOOTSTRAP_PASSWORD")
    origins = tuple(
        origin.strip()
        for origin in os.getenv(
            "ADMIN_TRUSTED_ORIGINS",
            "http://localhost:5173,https://app.redmoorconsulting.co.uk",
        ).split(",")
        if origin.strip()
    )
    cookie_samesite = os.getenv("ADMIN_SESSION_COOKIE_SAMESITE", "lax").strip().lower()
    if cookie_samesite not in {"lax", "strict"}:
        raise ValueError("ADMIN_SESSION_COOKIE_SAMESITE must be lax or strict")
    return AdminAuthenticationSettings(
        bootstrap_email=email.strip() if email and email.strip() else None,
        bootstrap_password=password if password else None,
        session_ttl_seconds=_env_int("ADMIN_SESSION_TTL_SECONDS", 8 * 60 * 60),
        cookie_name=os.getenv("ADMIN_SESSION_COOKIE_NAME", "redmoor_admin_session").strip(),
        cookie_secure=_env_bool("ADMIN_SESSION_COOKIE_SECURE", environment != "development"),
        cookie_samesite=cast(Literal["lax", "strict"], cookie_samesite),
        trusted_origins=origins,
        login_max_failures=_env_int("ADMIN_LOGIN_MAX_FAILURES", 5),
        login_lockout_seconds=_env_int("ADMIN_LOGIN_LOCKOUT_SECONDS", 15 * 60),
        throttle_window_seconds=_env_int("ADMIN_LOGIN_THROTTLE_WINDOW_SECONDS", 60),
        throttle_ip_attempts=_env_int("ADMIN_LOGIN_THROTTLE_IP_ATTEMPTS", 20),
        throttle_email_attempts=_env_int("ADMIN_LOGIN_THROTTLE_EMAIL_ATTEMPTS", 10),
        throttle_global_attempts=_env_int("ADMIN_LOGIN_THROTTLE_GLOBAL_ATTEMPTS", 200),
    )


def get_max_upload_bytes() -> int:
    return _env_int("MAX_UPLOAD_MB", 25) * 1024 * 1024


def get_upload_dir() -> Path:
    return Path(os.getenv("UPLOAD_DIR", "uploads"))


def validate_startup_configuration() -> None:
    """Validate every operational limit before the application accepts traffic."""
    ai_settings = get_ai_settings()
    if ai_settings.provider != "openai":
        raise ValueError("AI_PROVIDER must be openai")
    if not ai_settings.openai_model:
        raise ValueError("OPENAI_MODEL must not be empty")
    if not ai_settings.embedding_model:
        raise ValueError("OPENAI_EMBEDDING_MODEL must not be empty")
    get_knowledge_persistence_settings()
    get_website_loader_settings()
    get_content_processing_settings()
    get_ingestion_retry_settings()
    get_ingestion_worker_settings()
    get_database_settings()
    get_health_check_settings()
    get_public_assistant_chat_settings()
    admin_auth = get_admin_authentication_settings()
    if get_max_upload_bytes() <= 0:
        raise ValueError("MAX_UPLOAD_MB must be greater than zero")
    if not get_upload_dir().as_posix().strip():
        raise ValueError("UPLOAD_DIR must not be empty")
    environment = os.getenv("APP_ENV", "development").strip().lower()
    if environment not in {"development", "test", "staging", "production"}:
        raise ValueError("APP_ENV must be development, test, staging, or production")
    if environment == "production":
        if not os.getenv("DATABASE_URL"):
            raise ValueError("DATABASE_URL is required in production")
        if not ai_settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required in production")
        if not admin_auth.cookie_secure:
            raise ValueError("ADMIN_SESSION_COOKIE_SECURE must be true in production")
