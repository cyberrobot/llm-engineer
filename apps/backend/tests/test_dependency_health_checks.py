import asyncio
from pathlib import Path

import redis

from operations.domain.health import HealthErrorCode, HealthStatus
from operations.infrastructure.health_checks import (
    OpenAIConfigurationHealthCheck,
    PostgresHealthCheck,
    RedisHealthCheck,
    UploadStorageHealthCheck,
)


class Cursor:
    def __init__(self, *, error=None, vector_available=True):
        self.error = error
        self.vector_available = vector_available
        self.executed = []
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.closed = True

    def execute(self, query):
        self.executed.append(query)
        if self.error:
            raise self.error

    def fetchone(self):
        return (self.vector_available,)


class Connection:
    def __init__(self, cursor):
        self.test_cursor = cursor
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.closed = True

    def cursor(self):
        return self.test_cursor


def test_postgres_check_validates_connectivity_and_vector_extension_and_releases_connection():
    cursor = Cursor()
    connection = Connection(cursor)

    result = asyncio.run(PostgresHealthCheck(lambda: connection).check())

    assert result.status is HealthStatus.healthy
    assert cursor.executed == [
        "SELECT 1",
        "SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')",
    ]
    assert cursor.closed is True
    assert connection.closed is True


def test_postgres_check_fails_readiness_when_vector_extension_is_missing():
    result = asyncio.run(
        PostgresHealthCheck(lambda: Connection(Cursor(vector_available=False))).check()
    )

    assert result.status is HealthStatus.unhealthy
    assert result.code is HealthErrorCode.dependency_misconfigured


def test_postgres_connection_failure_returns_safe_unavailable_code():
    def unavailable():
        raise ConnectionError("postgresql://user:secret@internal/database")

    result = asyncio.run(PostgresHealthCheck(unavailable).check())

    assert result.status is HealthStatus.unhealthy
    assert result.code is HealthErrorCode.dependency_unavailable
    assert "secret" not in result.model_dump_json()


class RedisClient:
    def __init__(self, *, error=None):
        self.error = error
        self.calls = []

    def ping(self):
        self.calls.append("ping")
        if self.error:
            raise self.error
        return True


def test_redis_check_uses_ping_without_reading_or_writing_keys():
    client = RedisClient()

    result = asyncio.run(RedisHealthCheck(client, required=False).check())

    assert result.status is HealthStatus.healthy
    assert result.required is False
    assert client.calls == ["ping"]


def test_redis_failure_returns_safe_unavailable_code():
    result = asyncio.run(
        RedisHealthCheck(RedisClient(error=ConnectionError("redis://:secret@internal"))).check()
    )

    assert result.status is HealthStatus.unhealthy
    assert result.code is HealthErrorCode.dependency_unavailable
    assert "secret" not in result.model_dump_json()


def test_redis_timeout_returns_typed_timeout_result():
    result = asyncio.run(RedisHealthCheck(RedisClient(error=redis.TimeoutError())).check())

    assert result.status is HealthStatus.unhealthy
    assert result.code is HealthErrorCode.dependency_timeout


def test_openai_diagnostic_validates_configuration_without_provider_request():
    healthy = asyncio.run(OpenAIConfigurationHealthCheck(api_key="configured").check())
    missing = asyncio.run(OpenAIConfigurationHealthCheck(api_key=None).check())

    assert healthy.status is HealthStatus.healthy
    assert missing.status is HealthStatus.unhealthy
    assert missing.code is HealthErrorCode.dependency_misconfigured
    assert "configured" not in healthy.model_dump_json()


def test_upload_storage_check_requires_a_writable_existing_parent(tmp_path):
    healthy = asyncio.run(UploadStorageHealthCheck(tmp_path / "uploads").check())
    missing_parent = tmp_path / "missing"
    missing_parent.mkdir()
    missing_parent.chmod(0o500)
    try:
        unhealthy = asyncio.run(UploadStorageHealthCheck(missing_parent / "uploads").check())
    finally:
        missing_parent.chmod(0o700)

    assert healthy.status is HealthStatus.healthy
    assert unhealthy.status is HealthStatus.unhealthy
    assert unhealthy.code is HealthErrorCode.dependency_unavailable
    assert str(Path(tmp_path)) not in unhealthy.model_dump_json()


def test_upload_storage_check_rejects_writable_regular_file(tmp_path):
    configured_path = tmp_path / "uploads"
    configured_path.write_text("not a directory")

    result = asyncio.run(UploadStorageHealthCheck(configured_path).check())

    assert result.status is HealthStatus.unhealthy
    assert result.code is HealthErrorCode.dependency_unavailable
