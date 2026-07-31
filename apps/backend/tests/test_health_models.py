from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from operations.domain.health import DependencyHealthResult, HealthErrorCode, HealthStatus


def test_dependency_health_result_serializes_constrained_status_and_optional_code():
    result = DependencyHealthResult(
        name="redis",
        status=HealthStatus.unhealthy,
        required=False,
        latency_ms=12,
        code=HealthErrorCode.dependency_unavailable,
        checked_at=datetime(2026, 7, 31, 15, 0, tzinfo=timezone.utc),
    )

    assert result.model_dump(mode="json") == {
        "name": "redis",
        "status": "unhealthy",
        "required": False,
        "latency_ms": 12,
        "code": "dependency_unavailable",
        "checked_at": "2026-07-31T15:00:00Z",
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("status", "broken"),
        ("latency_ms", -1),
        ("checked_at", datetime(2026, 7, 31, 15, 0)),
        ("name", ""),
    ],
)
def test_dependency_health_result_rejects_invalid_contract_values(field, value):
    values = {
        "name": "postgres",
        "status": HealthStatus.healthy,
        "required": True,
        "latency_ms": 0,
        "checked_at": datetime(2026, 7, 31, 15, 0, tzinfo=timezone.utc),
    }
    values[field] = value

    with pytest.raises(ValidationError):
        DependencyHealthResult(**values)


def test_dependency_health_result_normalizes_aware_timestamp_to_utc():
    result = DependencyHealthResult(
        name="postgres",
        status=HealthStatus.healthy,
        required=True,
        latency_ms=1,
        checked_at=datetime.fromisoformat("2026-07-31T16:00:00+01:00"),
    )

    assert result.checked_at == datetime(2026, 7, 31, 15, 0, tzinfo=timezone.utc)
    assert result.code is None
