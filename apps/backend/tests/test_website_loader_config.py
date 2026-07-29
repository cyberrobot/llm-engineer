import pytest

from assistant.api.dependencies import get_website_loader
from assistant.infrastructure.ingestion.website_loader import HttpWebsiteLoader
from core.config import WebsiteLoaderSettings, get_website_loader_settings


def test_website_loader_settings_are_environment_driven(monkeypatch):
    monkeypatch.setenv("INGESTION_TIMEOUT_SECONDS", "4.5")
    monkeypatch.setenv("INGESTION_MAX_PAGES", "12")
    monkeypatch.setenv("INGESTION_USER_AGENT", "knowledge-bot/2.0")
    monkeypatch.setenv("INGESTION_MAX_RESPONSE_SIZE", "2048")

    settings = get_website_loader_settings()

    assert settings == WebsiteLoaderSettings(
        timeout_seconds=4.5,
        max_pages=12,
        user_agent="knowledge-bot/2.0",
        max_response_size=2048,
    )


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("INGESTION_TIMEOUT_SECONDS", "0"),
        ("INGESTION_MAX_PAGES", "0"),
        ("INGESTION_USER_AGENT", "  "),
        ("INGESTION_MAX_RESPONSE_SIZE", "0"),
    ],
)
def test_website_loader_settings_reject_invalid_values(monkeypatch, name, value):
    monkeypatch.setenv(name, value)

    with pytest.raises(ValueError, match=name):
        get_website_loader_settings()


def test_dependency_injection_registers_http_website_loader():
    get_website_loader.cache_clear()

    loader = get_website_loader()

    assert isinstance(loader, HttpWebsiteLoader)
    get_website_loader.cache_clear()
