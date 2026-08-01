import pytest

from core.config import get_admin_authentication_settings, validate_startup_configuration


def test_development_deliberately_allows_missing_bootstrap_credentials(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("ADMIN_BOOTSTRAP_EMAIL", raising=False)
    monkeypatch.delenv("ADMIN_BOOTSTRAP_PASSWORD", raising=False)

    settings = get_admin_authentication_settings()

    assert settings.bootstrap_email is None
    assert settings.bootstrap_password is None
    assert settings.cookie_secure is False


def test_bootstrap_credentials_must_be_configured_together(monkeypatch):
    monkeypatch.setenv("ADMIN_BOOTSTRAP_EMAIL", "admin@example.com")
    monkeypatch.delenv("ADMIN_BOOTSTRAP_PASSWORD", raising=False)
    with pytest.raises(ValueError, match="configured together"):
        get_admin_authentication_settings()


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("ADMIN_SESSION_TTL_SECONDS", "0"),
        ("ADMIN_LOGIN_MAX_FAILURES", "0"),
        ("ADMIN_LOGIN_LOCKOUT_SECONDS", "-1"),
        ("ADMIN_LOGIN_THROTTLE_WINDOW_SECONDS", "invalid"),
        ("ADMIN_SESSION_COOKIE_SAMESITE", "none"),
        ("ADMIN_TRUSTED_ORIGINS", "not-an-origin"),
    ],
)
def test_invalid_administrator_security_configuration_fails_clearly(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError, match=name):
        get_admin_authentication_settings()


def test_production_rejects_insecure_administrator_cookie(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://configured")
    monkeypatch.setenv("OPENAI_API_KEY", "configured")
    monkeypatch.setenv("ADMIN_SESSION_COOKIE_SECURE", "false")
    with pytest.raises(ValueError, match="ADMIN_SESSION_COOKIE_SECURE"):
        validate_startup_configuration()
