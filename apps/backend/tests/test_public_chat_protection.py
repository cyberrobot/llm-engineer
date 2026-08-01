from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from limits.storage import MemoryStorage

from assistant.api.dependencies import (
    get_public_chat_protection,
    get_public_chat_service_factory,
)
from assistant.application.public_chat_protection import (
    AnonymousClientResolver,
    InMemoryConcurrencyLimiter,
    PublicChatProtection,
    PublicChatRateLimiter,
    RedisLockConcurrencyLimiter,
    TokenBudget,
)
from core.config import PublicAssistantChatSettings, get_public_assistant_chat_settings
from main import app


def protection_settings(**overrides) -> PublicAssistantChatSettings:
    settings = PublicAssistantChatSettings.development_defaults(enabled=True)
    return replace(settings, **overrides)


def test_production_public_chat_enablement_fails_closed_without_mandatory_settings(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("PUBLIC_ASSISTANT_CHAT_ENABLED", "true")
    for name in PublicAssistantChatSettings.production_environment_names():
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(ValueError, match="PUBLIC_CHAT_ALLOWED_ORIGINS"):
        get_public_assistant_chat_settings()


def test_production_public_chat_accepts_only_complete_explicit_protection_configuration(
    monkeypatch,
):
    values = {
        "PUBLIC_CHAT_ALLOWED_ORIGINS": "https://www.example.test",
        "PUBLIC_CHAT_TRUSTED_PROXIES": "10.0.0.0/8",
        "FORWARDED_ALLOW_IPS": "10.0.0.0/8",
        "PUBLIC_CHAT_CLIENT_KEY_HASH_SECRET": "a" * 32,
        "PUBLIC_CHAT_MAX_MESSAGE_CHARACTERS": "4000",
        "PUBLIC_CHAT_MAX_HISTORY_MESSAGE_CHARACTERS": "4000",
        "PUBLIC_CHAT_MAX_HISTORY_MESSAGES": "12",
        "PUBLIC_CHAT_MAX_HISTORY_CHARACTERS": "12000",
        "PUBLIC_CHAT_MAX_HISTORY_TOKENS": "12000",
        "PUBLIC_CHAT_MAX_REQUEST_BYTES": "32768",
        "PUBLIC_CHAT_MAX_INPUT_TOKENS": "8000",
        "PUBLIC_CHAT_MAX_CONTEXT_CHUNKS": "3",
        "PUBLIC_CHAT_MAX_CONTEXT_TOKENS": "4000",
        "PUBLIC_CHAT_MODEL_CONTEXT_TOKENS": "1050000",
        "PUBLIC_CHAT_MAX_OUTPUT_TOKENS": "500",
        "PUBLIC_CHAT_MAX_ESTIMATED_COST": "0.10",
        "PUBLIC_CHAT_RATE_LIMIT_PER_MINUTE": "10",
        "PUBLIC_CHAT_RATE_LIMIT_PER_HOUR": "100",
        "PUBLIC_CHAT_GLOBAL_RATE_LIMIT_PER_MINUTE": "300",
        "PUBLIC_CHAT_MAX_CONCURRENT_REQUESTS_PER_CLIENT": "2",
        "PUBLIC_CHAT_MAX_CONCURRENT_REQUESTS_GLOBAL": "20",
        "PUBLIC_CHAT_REQUEST_TIMEOUT_SECONDS": "45",
        "PUBLIC_CHAT_MODEL_FIRST_TOKEN_TIMEOUT_SECONDS": "15",
        "REDIS_URL": "redis://shared-protection:6379/0",
    }
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("PUBLIC_ASSISTANT_CHAT_ENABLED", "true")
    monkeypatch.setenv("DISABLE_RATE_LIMITS", "false")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5.5")
    for name, value in values.items():
        monkeypatch.setenv(name, value)

    settings = get_public_assistant_chat_settings()

    assert settings.enabled is True
    assert settings.allowed_origins == ("https://www.example.test",)
    assert settings.trusted_proxy_networks == ("10.0.0.0/8",)


def test_configuration_rejects_wildcard_origin_and_unsafe_model_budget():
    with pytest.raises(ValueError, match="wildcard"):
        protection_settings(allowed_origins=("*",))
    with pytest.raises(ValueError, match="estimated cost"):
        protection_settings(maximum_estimated_cost_usd=0.000001)


def test_disabled_public_route_does_not_restrict_models_used_by_private_routes(monkeypatch):
    monkeypatch.setenv("PUBLIC_ASSISTANT_CHAT_ENABLED", "false")
    monkeypatch.setenv("OPENAI_MODEL", "private-route-model")

    settings = get_public_assistant_chat_settings()

    assert settings.enabled is False


def test_client_resolver_ignores_forwarding_headers_from_untrusted_peer():
    resolver = AnonymousClientResolver(("10.0.0.0/8",), hash_secret="test-secret")

    identity = resolver.resolve(
        peer_ip="203.0.113.10",
        forwarded_for="198.51.100.8",
        anonymous_session="rotating-id",
    )

    assert identity.resolved_ip == "203.0.113.10"
    assert identity.client_key != "203.0.113.10"
    assert "rotating-id" not in identity.client_key


def test_client_resolver_uses_framework_resolved_peer_and_never_raw_forwarding_header():
    resolver = AnonymousClientResolver(("10.0.0.0/8",), hash_secret="test-secret")

    identity = resolver.resolve(
        peer_ip="198.51.100.8",
        forwarded_for="203.0.113.99",
        anonymous_session=None,
    )

    assert identity.resolved_ip == "198.51.100.8"


def test_rate_limiter_enforces_exact_client_boundary_and_retry_after():
    settings = protection_settings(
        rate_limit_per_minute=2,
        rate_limit_per_hour=10,
        global_rate_limit_per_minute=20,
    )
    limiter = PublicChatRateLimiter(settings, storage=MemoryStorage(), clock=lambda: 100.0)

    assert limiter.check("client-a").allowed is True
    assert limiter.check("client-a").allowed is True
    rejected = limiter.check("client-a")

    assert rejected.allowed is False
    assert rejected.retry_after_seconds >= 1
    assert limiter.check("client-b").allowed is True


def test_concurrency_release_is_idempotent_and_global_failure_releases_client_slot():
    limiter = InMemoryConcurrencyLimiter(per_client=1, global_limit=1)
    first = limiter.acquire("client-a")

    with pytest.raises(RuntimeError, match="global_concurrency_limit_exceeded"):
        limiter.acquire("client-b")

    first.release()
    first.release()
    second = limiter.acquire("client-b")
    second.release()
    assert limiter.active_global == 0
    assert limiter.active_for("client-a") == 0
    assert limiter.active_for("client-b") == 0


def test_redis_concurrency_slots_are_shared_and_releasable_across_stream_threads():
    class FakeLock:
        def __init__(self, state, name):
            self.state = state
            self.name = name
            self.owned = False

        def acquire(self, *, blocking):
            assert blocking is False
            if self.name in self.state:
                return False
            self.state.add(self.name)
            self.owned = True
            return True

        def release(self):
            if self.owned:
                self.state.remove(self.name)
                self.owned = False

    class FakeRedis:
        def __init__(self):
            self.state = set()
            self.thread_local_values = []

        def lock(self, name, *, timeout, blocking_timeout, thread_local):
            assert timeout == 50
            assert blocking_timeout == 0
            self.thread_local_values.append(thread_local)
            return FakeLock(self.state, name)

    redis = FakeRedis()
    first_instance = RedisLockConcurrencyLimiter(
        redis,
        per_client=1,
        global_limit=1,
        lease_seconds=50,  # type: ignore[arg-type]
    )
    second_instance = RedisLockConcurrencyLimiter(
        redis,
        per_client=1,
        global_limit=1,
        lease_seconds=50,  # type: ignore[arg-type]
    )

    first = first_instance.acquire("client-a")
    with pytest.raises(RuntimeError, match="global_concurrency_limit_exceeded"):
        second_instance.acquire("client-b")
    first.release()
    second = second_instance.acquire("client-b")
    second.release()

    assert redis.state == set()
    assert set(redis.thread_local_values) == {False}


def test_token_budget_keeps_complete_relevance_ordered_chunks_and_reserves_output():
    budget = TokenBudget(
        max_input_tokens=120,
        max_context_tokens=30,
        max_context_chunks=2,
        model_context_tokens=200,
        output_tokens=50,
    )

    selected = budget.select_context(["a" * 10, "b" * 10, "c" * 10])

    assert selected == ("a" * 10, "b" * 10)
    assert budget.validate_prompt("system", "x" * 40) <= 120


def test_early_route_protections_reject_without_constructing_chat_service(monkeypatch):
    monkeypatch.setenv("PUBLIC_ASSISTANT_CHAT_ENABLED", "true")
    monkeypatch.setenv("PUBLIC_CHAT_ALLOWED_ORIGINS", "https://www.example.test")
    protector = PublicChatProtection.for_tests(protection_settings())
    app.dependency_overrides[get_public_chat_protection] = lambda: protector
    app.dependency_overrides[get_public_chat_service_factory] = lambda: (
        lambda: (_ for _ in ()).throw(
            AssertionError("early rejections must not construct chat orchestration")
        )
    )
    try:
        client = TestClient(app)
        wrong_type = client.post(
            "/public/assistants/redmoor/chat",
            content="message=hello",
            headers={"content-type": "application/x-www-form-urlencoded"},
        )
        wrong_origin = client.post(
            "/public/assistants/redmoor/chat",
            json={"message": "hello"},
            headers={"origin": "https://evil.example"},
        )
    finally:
        app.dependency_overrides.pop(get_public_chat_protection, None)
        app.dependency_overrides.pop(get_public_chat_service_factory, None)

    assert wrong_type.status_code == 415
    assert wrong_type.json()["detail"]["code"] == "unsupported_media_type"
    assert wrong_origin.status_code == 403
    assert wrong_origin.json()["detail"]["code"] == "origin_not_allowed"


def test_public_chat_cors_preflight_is_strict_and_does_not_construct_chat_service(monkeypatch):
    monkeypatch.setenv("PUBLIC_ASSISTANT_CHAT_ENABLED", "true")
    monkeypatch.setenv("PUBLIC_CHAT_ALLOWED_ORIGINS", "https://www.example.test")
    app.dependency_overrides[get_public_chat_service_factory] = lambda: (
        lambda: (_ for _ in ()).throw(
            AssertionError("preflight must not construct chat orchestration")
        )
    )
    try:
        client = TestClient(app)
        accepted = client.options(
            "/public/assistants/redmoor/chat",
            headers={
                "origin": "https://www.example.test",
                "access-control-request-method": "POST",
                "access-control-request-headers": "Content-Type, X-Anonymous-Session-ID",
            },
        )
        broad_headers = client.options(
            "/public/assistants/redmoor/chat",
            headers={
                "origin": "https://www.example.test",
                "access-control-request-method": "POST",
                "access-control-request-headers": "Authorization",
            },
        )
    finally:
        app.dependency_overrides.pop(get_public_chat_service_factory, None)

    assert accepted.status_code == 204
    assert accepted.headers["access-control-allow-origin"] == "https://www.example.test"
    assert accepted.headers["access-control-allow-methods"] == "POST, OPTIONS"
    assert "access-control-allow-credentials" not in accepted.headers
    assert broad_headers.status_code == 403


def test_raw_request_limit_counts_utf8_bytes_before_json_parsing(monkeypatch):
    monkeypatch.setenv("PUBLIC_ASSISTANT_CHAT_ENABLED", "true")
    monkeypatch.setenv("PUBLIC_CHAT_MAX_REQUEST_BYTES", "24")
    body = '{"message":"🙂🙂🙂"}'.encode()

    response = TestClient(app).post(
        "/public/assistants/redmoor/chat",
        content=body,
        headers={"content-type": "application/json"},
    )

    assert len(body) > 24
    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "request_too_large"


def test_malformed_json_has_stable_pre_stream_error(monkeypatch):
    monkeypatch.setenv("PUBLIC_ASSISTANT_CHAT_ENABLED", "true")

    response = TestClient(app).post(
        "/public/assistants/redmoor/chat",
        content=b'{"message":',
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "invalid_request"


def test_configured_message_limit_returns_stable_error_before_orchestration(monkeypatch):
    get_public_chat_protection.cache_clear()
    monkeypatch.setenv("PUBLIC_ASSISTANT_CHAT_ENABLED", "true")
    monkeypatch.setenv("PUBLIC_CHAT_MAX_MESSAGE_CHARACTERS", "5")
    app.dependency_overrides[get_public_chat_service_factory] = lambda: (
        lambda: (_ for _ in ()).throw(
            AssertionError("message-limit rejection must not construct chat orchestration")
        )
    )
    try:
        response = TestClient(app).post(
            "/public/assistants/redmoor/chat",
            json={"message": "123456"},
        )
    finally:
        app.dependency_overrides.pop(get_public_chat_service_factory, None)
        get_public_chat_protection.cache_clear()

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "message_too_long"
