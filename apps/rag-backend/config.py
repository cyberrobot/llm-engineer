import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str | None = os.getenv("RAG_DATABASE_URL")
    redis_url: str = os.getenv("RAG_REDIS_URL", "redis://localhost:6379/1")
    openai_api_key: str | None = os.getenv("RAG_OPENAI_API_KEY")
    chat_model: str = os.getenv("RAG_CHAT_MODEL", "gpt-5.4-nano")
    embedding_model: str = os.getenv("RAG_EMBEDDING_MODEL", "text-embedding-3-small")
    provider_timeout_seconds: float = float(
        os.getenv("RAG_PROVIDER_TIMEOUT_SECONDS", "30")
    )
    request_timeout_seconds: float = float(
        os.getenv("RAG_REQUEST_TIMEOUT_SECONDS", "45")
    )
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
        if "*" in self.allowed_origins:
            raise ValueError("RAG_ALLOWED_ORIGINS must not contain a wildcard")
        if self.provider_timeout_seconds <= 0 or self.request_timeout_seconds <= 0:
            raise ValueError("RAG timeouts must be positive")


settings = Settings()
