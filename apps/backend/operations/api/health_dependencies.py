import os

from core.config import get_ai_settings, get_health_check_settings, get_upload_dir
from infrastructure.cache.client import redis_client
from infrastructure.database.connection import get_connection
from operations.application.health import HealthCheck, HealthService
from operations.infrastructure.health_checks import (
    ApplicationHealthCheck,
    OpenAIConfigurationHealthCheck,
    PostgresHealthCheck,
    RedisHealthCheck,
    UploadStorageHealthCheck,
)


def get_health_service() -> HealthService:
    """Compose checks from configured dependencies while reusing managed clients."""
    settings = get_health_check_settings()
    checks: list[HealthCheck] = [
        ApplicationHealthCheck(),
        UploadStorageHealthCheck(get_upload_dir()),
    ]
    if os.getenv("DATABASE_URL"):
        checks.append(PostgresHealthCheck(get_connection))
    if not settings.redis_disabled:
        checks.append(RedisHealthCheck(redis_client, required=False))
    ai_settings = get_ai_settings()
    if ai_settings.provider == "openai":
        checks.append(OpenAIConfigurationHealthCheck(api_key=ai_settings.openai_api_key))
    return HealthService(checks, timeout_seconds=settings.timeout_seconds)
