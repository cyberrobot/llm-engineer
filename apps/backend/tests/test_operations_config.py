import pytest

from core.config import get_admin_api_key


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
