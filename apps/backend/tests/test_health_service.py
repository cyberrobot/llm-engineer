import asyncio
from dataclasses import dataclass

from operations.application.health import HealthService
from operations.domain.health import DependencyHealthResult, HealthErrorCode, HealthStatus


@dataclass
class FakeCheck:
    name: str
    required: bool
    status: HealthStatus
    yield_before_result: bool = False

    async def check(self) -> DependencyHealthResult:
        if self.yield_before_result:
            await asyncio.sleep(0)
        return DependencyHealthResult.create(
            name=self.name,
            status=self.status,
            required=self.required,
            latency_ms=0,
        )


class NeverCompletesCheck:
    name = "slow"
    required = True

    async def check(self) -> DependencyHealthResult:
        await asyncio.Event().wait()
        raise AssertionError("unreachable")


class ExplodingCheck:
    name = "broken"
    required = False

    async def check(self) -> DependencyHealthResult:
        raise RuntimeError("secret raw failure")


def aggregate(*checks, timeout_seconds=1):
    return asyncio.run(HealthService(checks, timeout_seconds=timeout_seconds).diagnose())


def test_all_healthy_checks_produce_healthy_ready_result_in_registration_order():
    result = aggregate(
        FakeCheck("postgres", True, HealthStatus.healthy, yield_before_result=True),
        FakeCheck("redis", False, HealthStatus.healthy),
    )

    assert result.status is HealthStatus.healthy
    assert result.ready is True
    assert [check.name for check in result.checks] == ["postgres", "redis"]


def test_optional_failure_degrades_diagnostics_without_failing_readiness():
    result = aggregate(
        FakeCheck("postgres", True, HealthStatus.healthy),
        FakeCheck("redis", False, HealthStatus.unhealthy),
    )

    assert result.status is HealthStatus.degraded
    assert result.ready is True


def test_required_failure_is_unhealthy_and_not_ready():
    result = aggregate(FakeCheck("postgres", True, HealthStatus.unhealthy))

    assert result.status is HealthStatus.unhealthy
    assert result.ready is False


def test_unknown_required_result_fails_readiness_safely():
    result = aggregate(FakeCheck("postgres", True, HealthStatus.unknown))

    assert result.status is HealthStatus.unhealthy
    assert result.ready is False


def test_empty_check_set_is_healthy_and_ready():
    result = aggregate()

    assert result.status is HealthStatus.healthy
    assert result.ready is True
    assert result.checks == ()


def test_timeout_and_unexpected_failure_are_typed_without_suppressing_other_results():
    result = aggregate(
        NeverCompletesCheck(),
        FakeCheck("postgres", True, HealthStatus.healthy),
        ExplodingCheck(),
        timeout_seconds=0.01,
    )

    assert [check.name for check in result.checks] == ["slow", "postgres", "broken"]
    assert result.checks[0].status is HealthStatus.unhealthy
    assert result.checks[0].code is HealthErrorCode.dependency_timeout
    assert result.checks[1].status is HealthStatus.healthy
    assert result.checks[2].status is HealthStatus.unknown
    assert result.checks[2].code is HealthErrorCode.dependency_check_failed
    assert "secret raw failure" not in result.model_dump_json()
