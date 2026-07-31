import pytest

from core.config import get_admin_api_key, get_health_check_settings


def test_configured_admin_api_key_loads_without_transforming_the_secret(monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "configured-admin-secret")

    assert get_admin_api_key() == "configured-admin-secret"


@pytest.mark.parametrize("value", [None, "", "   "])
def test_missing_or_blank_admin_api_key_has_secure_unconfigured_default(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("ADMIN_API_KEY", raising=False)
    else:
        monkeypatch.setenv("ADMIN_API_KEY", value)

    assert get_admin_api_key() is None


def test_health_check_settings_have_short_default_and_derive_redis_enablement(monkeypatch):
    monkeypatch.delenv("HEALTH_CHECK_TIMEOUT_SECONDS", raising=False)
    monkeypatch.setenv("DISABLE_CACHE", "true")

    settings = get_health_check_settings()

    assert settings.timeout_seconds == 2
    assert settings.redis_disabled is True


@pytest.mark.parametrize("value", ["0", "-1", "11", "not-a-number"])
def test_health_check_timeout_rejects_unbounded_or_invalid_values(monkeypatch, value):
    monkeypatch.setenv("HEALTH_CHECK_TIMEOUT_SECONDS", value)

    with pytest.raises(ValueError, match="HEALTH_CHECK_TIMEOUT_SECONDS"):
        get_health_check_settings()
