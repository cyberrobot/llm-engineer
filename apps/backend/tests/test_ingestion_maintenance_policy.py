from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from assistant.maintenance.ingestion import IngestionMaintenanceSettings

NOW = datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc)


def test_maintenance_settings_use_conservative_retention_defaults():
    settings = IngestionMaintenanceSettings()

    assert settings.completed_job_retention_days == 90
    assert settings.failed_job_retention_days == 180
    assert settings.cancelled_job_retention_days == 90
    assert settings.step_history_retention_days == 90
    assert settings.superseded_representation_retention_days == 30
    assert settings.temporary_source_retention_hours == 24
    assert settings.batch_size == 100
    assert settings.max_batches == 20


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("completed_job_retention_days", -1),
        ("failed_job_retention_days", -1),
        ("cancelled_job_retention_days", -1),
        ("step_history_retention_days", -1),
        ("superseded_representation_retention_days", -1),
        ("temporary_source_retention_hours", -1),
        ("temporary_source_retention_hours", 0),
        ("batch_size", 0),
        ("max_batches", 0),
        ("lock_timeout_seconds", -1),
        ("stale_job_grace_seconds", -1),
    ],
)
def test_maintenance_settings_reject_invalid_limits(field, value):
    with pytest.raises(ValueError, match=field.upper()):
        replace(IngestionMaintenanceSettings(), **{field: value})


def test_cutoffs_are_utc_aware_and_status_specific_at_the_boundary():
    settings = IngestionMaintenanceSettings(
        completed_job_retention_days=10,
        failed_job_retention_days=20,
        cancelled_job_retention_days=30,
    )

    cutoffs = settings.job_cutoffs(NOW)

    assert cutoffs["completed"] == NOW - timedelta(days=10)
    assert cutoffs["failed"] == NOW - timedelta(days=20)
    assert cutoffs["cancelled"] == NOW - timedelta(days=30)
    with pytest.raises(ValueError, match="timezone-aware"):
        settings.job_cutoffs(NOW.replace(tzinfo=None))
