from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from pydantic import ValidationError

from operations.domain.operation import OperationalAction, OperationStatus


def test_operational_action_serializes_stable_validated_metadata_as_utc_json():
    action = OperationalAction(
        operation_id=UUID("12345678-1234-5678-1234-567812345678"),
        operation_type="cache_invalidation",
        requested_at=datetime(2026, 7, 31, 11, 30, tzinfo=timezone(timedelta(hours=1))),
        requested_by="admin-api-key",
        status=OperationStatus.accepted,
    )

    assert action.requested_at == datetime(2026, 7, 31, 10, 30, tzinfo=timezone.utc)
    assert action.model_dump(mode="json") == {
        "operation_id": "12345678-1234-5678-1234-567812345678",
        "operation_type": "cache_invalidation",
        "requested_at": "2026-07-31T10:30:00Z",
        "requested_by": "admin-api-key",
        "status": "accepted",
    }
    assert action.model_dump_json() == (
        '{"operation_id":"12345678-1234-5678-1234-567812345678",'
        '"operation_type":"cache_invalidation","requested_at":"2026-07-31T10:30:00Z",'
        '"requested_by":"admin-api-key","status":"accepted"}'
    )


def test_operational_action_generates_one_uuid_identity_per_action():
    requested_at = datetime(2026, 7, 31, 10, 30, tzinfo=timezone.utc)

    first = OperationalAction(
        operation_type="configuration_reload",
        requested_at=requested_at,
        requested_by="admin-api-key",
    )
    serialized_once = first.model_dump(mode="json")["operation_id"]
    serialized_twice = first.model_dump(mode="json")["operation_id"]
    second = OperationalAction(
        operation_type="configuration_reload",
        requested_at=requested_at,
        requested_by="admin-api-key",
    )

    assert UUID(serialized_once)
    assert serialized_once == serialized_twice
    assert first.operation_id != second.operation_id


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("status", "unknown"),
        ("operation_type", "Cache Invalidation"),
        ("operation_type", ""),
        ("requested_by", ""),
        ("requested_at", datetime(2026, 7, 31, 10, 30)),
        ("operation_id", "not-a-uuid"),
    ],
)
def test_operational_action_rejects_invalid_metadata(field, value):
    values = {
        "operation_id": UUID("12345678-1234-5678-1234-567812345678"),
        "operation_type": "cache_invalidation",
        "requested_at": datetime(2026, 7, 31, 10, 30, tzinfo=timezone.utc),
        "requested_by": "admin-api-key",
        "status": OperationStatus.accepted,
    }
    values[field] = value

    with pytest.raises(ValidationError):
        OperationalAction(**values)
