import asyncio
import logging
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from time import perf_counter
from typing import Protocol

from operations.domain.health import (
    DependencyHealthResult,
    HealthDiagnostic,
    HealthErrorCode,
    HealthStatus,
)

logger = logging.getLogger(__name__)


class HealthCheck(Protocol):
    name: str
    required: bool

    async def check(self) -> DependencyHealthResult: ...


class HealthService:
    """Run independent checks concurrently and derive diagnostic/readiness state."""

    def __init__(
        self,
        checks: Sequence[HealthCheck],
        *,
        timeout_seconds: float,
        now: Callable[[], datetime] | None = None,
        timer: Callable[[], float] = perf_counter,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("Health check timeout must be greater than zero")
        self._checks = tuple(checks)
        self._timeout_seconds = timeout_seconds
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._timer = timer

    async def diagnose(self) -> HealthDiagnostic:
        results = await asyncio.gather(*(self._run_check(check) for check in self._checks))
        status, ready = self._aggregate(results)
        return HealthDiagnostic(
            status=status,
            ready=ready,
            generated_at=self._now(),
            checks=tuple(results),
        )

    async def _run_check(self, check: HealthCheck) -> DependencyHealthResult:
        started = self._timer()
        checked_at = self._now()
        try:
            async with asyncio.timeout(self._timeout_seconds):
                result = await check.check()
        except TimeoutError:
            result = DependencyHealthResult.create(
                name=check.name,
                status=HealthStatus.unhealthy,
                required=check.required,
                latency_ms=0,
                code=HealthErrorCode.dependency_timeout,
                checked_at=checked_at,
            )
        except Exception:
            logger.exception(
                "health_check_failed_unexpectedly",
                extra={
                    "check_name": check.name,
                    "health_status": HealthStatus.unknown.value,
                    "error_code": HealthErrorCode.dependency_check_failed.value,
                    "required": check.required,
                },
            )
            result = DependencyHealthResult.create(
                name=check.name,
                status=HealthStatus.unknown,
                required=check.required,
                latency_ms=0,
                code=HealthErrorCode.dependency_check_failed,
                checked_at=checked_at,
            )

        latency_ms = max(0, round((self._timer() - started) * 1_000))
        result = result.model_copy(
            update={
                "name": check.name,
                "required": check.required,
                "latency_ms": latency_ms,
                "checked_at": checked_at,
            }
        )
        self._log_failure(result)
        return result

    @staticmethod
    def _aggregate(
        checks: Sequence[DependencyHealthResult],
    ) -> tuple[HealthStatus, bool]:
        required_failed = any(
            check.required and check.status is not HealthStatus.healthy for check in checks
        )
        optional_failed = any(
            not check.required and check.status is not HealthStatus.healthy for check in checks
        )
        if required_failed:
            return HealthStatus.unhealthy, False
        if optional_failed:
            return HealthStatus.degraded, True
        return HealthStatus.healthy, True

    @staticmethod
    def _log_failure(result: DependencyHealthResult) -> None:
        if result.status is HealthStatus.healthy:
            return
        log = logger.error if result.required else logger.warning
        log(
            "dependency_health_check_failed",
            extra={
                "check_name": result.name,
                "health_status": result.status.value,
                "error_code": result.code.value if result.code else None,
                "latency_ms": result.latency_ms,
                "required": result.required,
            },
        )
