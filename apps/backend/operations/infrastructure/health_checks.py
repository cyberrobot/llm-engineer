import asyncio
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import psycopg
import redis

from operations.domain.health import DependencyHealthResult, HealthErrorCode, HealthStatus


class ApplicationHealthCheck:
    name = "application"
    required = True

    async def check(self) -> DependencyHealthResult:
        return _result(self.name, self.required, HealthStatus.healthy)


class PostgresHealthCheck:
    name = "postgres"
    required = True

    def __init__(self, connection_factory: Callable[[], Any]) -> None:
        self._connection_factory = connection_factory

    async def check(self) -> DependencyHealthResult:
        try:
            await asyncio.to_thread(self._select_one)
        except _MissingVectorExtension:
            return _result(
                self.name,
                self.required,
                HealthStatus.unhealthy,
                HealthErrorCode.dependency_misconfigured,
            )
        except (psycopg.OperationalError, ConnectionError, OSError):
            return _result(
                self.name,
                self.required,
                HealthStatus.unhealthy,
                HealthErrorCode.dependency_unavailable,
            )
        except psycopg.Error as exc:
            code = (
                HealthErrorCode.dependency_authentication_failed
                if getattr(exc, "sqlstate", "") in {"28000", "28P01"}
                else HealthErrorCode.dependency_check_failed
            )
            return _result(self.name, self.required, HealthStatus.unhealthy, code)
        return _result(self.name, self.required, HealthStatus.healthy)

    def _select_one(self) -> None:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.execute(
                    "SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')"
                )
                row = cursor.fetchone()
                if not row or not bool(row[0]):
                    raise _MissingVectorExtension


class _MissingVectorExtension(RuntimeError):
    pass


class UploadStorageHealthCheck:
    name = "upload_storage"
    required = True

    def __init__(self, path: Path) -> None:
        self._path = path

    async def check(self) -> DependencyHealthResult:
        target = self._path.expanduser().resolve()
        if target.exists():
            ready = target.is_dir() and os.access(target, os.W_OK)
        else:
            parent = self._existing_parent(target)
            ready = parent.is_dir() and os.access(parent, os.W_OK)
        if not ready:
            return _result(
                self.name,
                self.required,
                HealthStatus.unhealthy,
                HealthErrorCode.dependency_unavailable,
            )
        return _result(self.name, self.required, HealthStatus.healthy)

    @staticmethod
    def _existing_parent(path: Path) -> Path:
        candidate = path.expanduser().resolve()
        while not candidate.exists() and candidate != candidate.parent:
            candidate = candidate.parent
        return candidate


class RedisHealthCheck:
    name = "redis"

    def __init__(self, client: Any, *, required: bool = False) -> None:
        self._client = client
        self.required = required

    async def check(self) -> DependencyHealthResult:
        try:
            await asyncio.to_thread(self._client.ping)
        except redis.AuthenticationError:
            return _result(
                self.name,
                self.required,
                HealthStatus.unhealthy,
                HealthErrorCode.dependency_authentication_failed,
            )
        except (redis.TimeoutError, TimeoutError):
            return _result(
                self.name,
                self.required,
                HealthStatus.unhealthy,
                HealthErrorCode.dependency_timeout,
            )
        except (redis.RedisError, ConnectionError, OSError):
            return _result(
                self.name,
                self.required,
                HealthStatus.unhealthy,
                HealthErrorCode.dependency_unavailable,
            )
        return _result(self.name, self.required, HealthStatus.healthy)


class OpenAIConfigurationHealthCheck:
    name = "openai"
    required = False

    def __init__(self, *, api_key: str | None) -> None:
        self._configured = bool(api_key and api_key.strip())

    async def check(self) -> DependencyHealthResult:
        if not self._configured:
            return _result(
                self.name,
                self.required,
                HealthStatus.unhealthy,
                HealthErrorCode.dependency_misconfigured,
            )
        return _result(self.name, self.required, HealthStatus.healthy)


def _result(
    name: str,
    required: bool,
    status: HealthStatus,
    code: HealthErrorCode | None = None,
) -> DependencyHealthResult:
    return DependencyHealthResult.create(
        name=name,
        required=required,
        status=status,
        latency_ms=0,
        code=code,
    )
