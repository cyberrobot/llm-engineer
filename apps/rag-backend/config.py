import os
from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Settings:
    ai_provider: str = os.getenv("RAG_AI_PROVIDER", "openai")
    knowledge_database_url: str | None = os.getenv("RAG_KNOWLEDGE_DATABASE_URL")
    auth_audit_database_url: str | None = os.getenv("RAG_AUTH_AUDIT_DATABASE_URL")
    redis_url: str = os.getenv("RAG_REDIS_URL", "redis://localhost:6379/1")
    openai_api_key: str | None = os.getenv("RAG_OPENAI_API_KEY")
    chat_model: str = os.getenv("RAG_CHAT_MODEL", "gpt-5.4-nano")
    embedding_model: str = os.getenv("RAG_EMBEDDING_MODEL", "text-embedding-3-small")
    provider_timeout_seconds: float = float(
        os.getenv("RAG_PROVIDER_TIMEOUT_SECONDS", "30")
    )
    provider_max_retries: int = int(os.getenv("RAG_PROVIDER_MAX_RETRIES", "2"))
    request_timeout_seconds: float = float(
        os.getenv("RAG_REQUEST_TIMEOUT_SECONDS", "45")
    )
    health_timeout_seconds: float = float(os.getenv("RAG_HEALTH_TIMEOUT_SECONDS", "2"))
    allowed_origins: tuple[str, ...] = tuple(
        filter(
            None, os.getenv("RAG_ALLOWED_ORIGINS", "http://localhost:5173").split(",")
        )
    )
    session_cookie_name: str = os.getenv(
        "RAG_SESSION_COOKIE_NAME", "redmoor_admin_session"
    )
    audit_limit: int = 10
    max_message_characters: int = 4000
    max_request_bytes: int = 32768
    max_audit_limit: int = 200
    cache_ttl_seconds: int = 300
    disable_cache: bool = os.getenv("RAG_DISABLE_CACHE", "false").lower() == "true"
    disable_audit: bool = os.getenv("RAG_DISABLE_AUDIT_LOGS", "false").lower() == "true"

    def validate(self) -> None:
        if self.ai_provider != "openai":
            raise ValueError("RAG_AI_PROVIDER must be openai")
        if not self.allowed_origins:
            raise ValueError("RAG_ALLOWED_ORIGINS must contain at least one origin")
        for origin in self.allowed_origins:
            parsed = urlsplit(origin)
            if (
                origin == "*"
                or parsed.scheme not in {"http", "https"}
                or not parsed.netloc
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError(
                    "RAG_ALLOWED_ORIGINS must contain exact HTTP(S) origins"
                )
        if (
            self.provider_timeout_seconds <= 0
            or self.request_timeout_seconds <= 0
            or self.health_timeout_seconds <= 0
        ):
            raise ValueError("RAG timeouts must be positive")
        if self.provider_max_retries < 0:
            raise ValueError("RAG_PROVIDER_MAX_RETRIES must not be negative")

    def validate_runtime(self) -> None:
        self.validate()
        if not self.knowledge_database_url:
            raise ValueError("RAG_KNOWLEDGE_DATABASE_URL must be configured")
        if not self.auth_audit_database_url:
            raise ValueError("RAG_AUTH_AUDIT_DATABASE_URL must be configured")
        if not self.openai_api_key:
            raise ValueError("RAG_OPENAI_API_KEY must be configured")
        if not self.chat_model.strip() or not self.embedding_model.strip():
            raise ValueError("RAG model configuration must not be empty")
        if not self.redis_url and not self.disable_cache:
            raise ValueError("RAG_REDIS_URL must be configured when caching is enabled")


settings = Settings()
