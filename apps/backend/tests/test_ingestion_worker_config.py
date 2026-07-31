import pytest

from core.config import get_ingestion_worker_settings


def test_worker_settings_have_safe_defaults_and_generated_identity(monkeypatch):
    for name in (
        "INGESTION_WORKER_ENABLED",
        "INGESTION_WORKER_POLL_INTERVAL_SECONDS",
        "INGESTION_WORKER_LEASE_SECONDS",
        "INGESTION_WORKER_HEARTBEAT_INTERVAL_SECONDS",
        "INGESTION_WORKER_CONCURRENCY",
        "INGESTION_WORKER_SHUTDOWN_GRACE_SECONDS",
        "INGESTION_WORKER_ID",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = get_ingestion_worker_settings()

    assert settings.enabled is True
    assert settings.poll_interval_seconds == 1
    assert settings.lease_seconds == 60
    assert settings.heartbeat_interval_seconds == 20
    assert settings.concurrency == 1
    assert settings.shutdown_grace_seconds == 30
    assert settings.worker_id


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("INGESTION_WORKER_ENABLED", "sometimes", "must be true or false"),
        ("INGESTION_WORKER_POLL_INTERVAL_SECONDS", "0", "must be greater than zero"),
        ("INGESTION_WORKER_LEASE_SECONDS", "0", "must be greater than zero"),
        ("INGESTION_WORKER_HEARTBEAT_INTERVAL_SECONDS", "0", "must be greater than zero"),
        ("INGESTION_WORKER_CONCURRENCY", "0", "must be at least 1"),
        ("INGESTION_WORKER_SHUTDOWN_GRACE_SECONDS", "-1", "must not be negative"),
    ],
)
def test_worker_settings_reject_invalid_values(monkeypatch, name, value, message):
    monkeypatch.setenv(name, value)

    with pytest.raises(ValueError, match=message):
        get_ingestion_worker_settings()


def test_worker_settings_require_heartbeat_shorter_than_lease(monkeypatch):
    monkeypatch.setenv("INGESTION_WORKER_LEASE_SECONDS", "10")
    monkeypatch.setenv("INGESTION_WORKER_HEARTBEAT_INTERVAL_SECONDS", "10")

    with pytest.raises(ValueError, match="must be shorter"):
        get_ingestion_worker_settings()


def test_worker_settings_preserve_explicit_identity(monkeypatch):
    monkeypatch.setenv("INGESTION_WORKER_ID", "worker-test-1")

    assert get_ingestion_worker_settings().worker_id == "worker-test-1"
