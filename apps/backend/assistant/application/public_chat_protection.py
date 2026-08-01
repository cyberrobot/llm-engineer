import math
import threading
import time
from dataclasses import dataclass
from hashlib import sha256
from hmac import new as new_hmac
from ipaddress import ip_address
from typing import Callable, Protocol

from limits import RateLimitItemPerHour, RateLimitItemPerMinute
from limits.storage import Storage, storage_from_string
from limits.strategies import FixedWindowRateLimiter
from redis import Redis
from redis.exceptions import LockError, RedisError

from assistant.schemas.public_chat import PublicChatRequest
from core.config import PublicAssistantChatSettings


@dataclass(frozen=True, slots=True)
class AnonymousClientIdentity:
    resolved_ip: str
    client_key: str
    session_key: str | None


class AnonymousClientResolver:
    """Resolve proxy-aware IP identity and return only keyed hashes for enforcement."""

    def __init__(self, trusted_proxy_networks: tuple[str, ...], *, hash_secret: str) -> None:
        if not hash_secret.strip():
            raise ValueError("PUBLIC_CHAT_CLIENT_KEY_HASH_SECRET must not be empty")
        del trusted_proxy_networks
        self._secret = hash_secret.encode("utf-8")

    def resolve(
        self,
        *,
        peer_ip: str | None,
        forwarded_for: str | None,
        anonymous_session: str | None,
    ) -> AnonymousClientIdentity:
        resolved = self._normalise_ip(peer_ip)
        # Uvicorn resolves forwarding headers before application code and only from
        # FORWARDED_ALLOW_IPS. Never reinterpret a raw forwarding header here.
        del forwarded_for
        session_key = None
        if anonymous_session and 1 <= len(anonymous_session) <= 128:
            session_key = self._hash(f"session:{anonymous_session}")
        # The IP key remains authoritative, so rotating browser identifiers cannot bypass limits.
        return AnonymousClientIdentity(resolved, self._hash(f"ip:{resolved}"), session_key)

    @staticmethod
    def _normalise_ip(value: str | None) -> str:
        if not value:
            return "unknown"
        try:
            return str(ip_address(value))
        except ValueError:
            return "unknown"

    def _hash(self, value: str) -> str:
        return new_hmac(self._secret, value.encode("utf-8"), sha256).hexdigest()


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: int = 0


class PublicChatRateLimiter:
    """Atomic layered public throttling using the repository's limits library."""

    def __init__(
        self,
        settings: PublicAssistantChatSettings,
        *,
        storage: Storage | None = None,
        storage_uri: str | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if storage is None and storage_uri is None:
            raise ValueError("Public chat rate limiting requires shared storage")
        self._limiter = FixedWindowRateLimiter(storage or storage_from_string(str(storage_uri)))
        self._clock = clock
        self._rules = (
            (RateLimitItemPerMinute(settings.rate_limit_per_minute), "client-minute", True),
            (RateLimitItemPerHour(settings.rate_limit_per_hour), "client-hour", True),
            (
                RateLimitItemPerMinute(settings.global_rate_limit_per_minute),
                "global-minute",
                False,
            ),
        )

    def check(self, client_key: str) -> RateLimitDecision:
        retry_after = 0
        allowed = True
        for rule, namespace, per_client in self._rules:
            identifier = client_key if per_client else "all"
            if not self._limiter.hit(rule, "public-chat", namespace, identifier):
                allowed = False
                stats = self._limiter.get_window_stats(rule, "public-chat", namespace, identifier)
                retry_after = max(
                    retry_after,
                    max(1, math.ceil(stats.reset_time - self._clock())),
                )
        return RateLimitDecision(allowed, retry_after)


class ConcurrencyLease(Protocol):
    def release(self) -> None: ...


class ConcurrencyRejected(RuntimeError):
    pass


class _InMemoryLease:
    def __init__(self, limiter: "InMemoryConcurrencyLimiter", client_key: str) -> None:
        self._limiter = limiter
        self._client_key = client_key
        self._released = False
        self._lock = threading.Lock()

    def release(self) -> None:
        with self._lock:
            if self._released:
                return
            self._released = True
        self._limiter._release(self._client_key)


class InMemoryConcurrencyLimiter:
    """Immediate-rejection limiter used only for local development and tests."""

    def __init__(self, *, per_client: int, global_limit: int) -> None:
        self._per_client_limit = per_client
        self._global_limit = global_limit
        self._active_by_client: dict[str, int] = {}
        self._active_global = 0
        self._lock = threading.Lock()

    def acquire(self, client_key: str) -> ConcurrencyLease:
        with self._lock:
            client_active = self._active_by_client.get(client_key, 0)
            if client_active >= self._per_client_limit:
                raise ConcurrencyRejected("client_concurrency_limit_exceeded")
            self._active_by_client[client_key] = client_active + 1
            if self._active_global >= self._global_limit:
                self._decrement_client(client_key)
                raise ConcurrencyRejected("global_concurrency_limit_exceeded")
            self._active_global += 1
        return _InMemoryLease(self, client_key)

    def _release(self, client_key: str) -> None:
        with self._lock:
            self._decrement_client(client_key)
            if self._active_global > 0:
                self._active_global -= 1

    def _decrement_client(self, client_key: str) -> None:
        current = self._active_by_client.get(client_key, 0)
        if current <= 1:
            self._active_by_client.pop(client_key, None)
        else:
            self._active_by_client[client_key] = current - 1

    @property
    def active_global(self) -> int:
        with self._lock:
            return self._active_global

    def active_for(self, client_key: str) -> int:
        with self._lock:
            return self._active_by_client.get(client_key, 0)


class _RedisLockLease:
    def __init__(self, locks: tuple[object, ...]) -> None:
        self._locks = locks
        self._released = False
        self._guard = threading.Lock()

    def release(self) -> None:
        with self._guard:
            if self._released:
                return
            self._released = True
        for lock in reversed(self._locks):
            try:
                lock.release()  # type: ignore[attr-defined]
            except LockError:
                # A request timeout can race the Redis lease expiry; release stays idempotent.
                continue


class RedisLockConcurrencyLimiter:
    """Deployment-wide bounded slots backed by redis-py's owned lock primitive."""

    def __init__(
        self,
        redis_client: Redis,
        *,
        per_client: int,
        global_limit: int,
        lease_seconds: float,
    ) -> None:
        self._redis = redis_client
        self._per_client = per_client
        self._global = global_limit
        self._lease_seconds = lease_seconds

    def acquire(self, client_key: str) -> ConcurrencyLease:
        client_lock = self._acquire_slot(f"public-chat:client:{client_key}", self._per_client)
        if client_lock is None:
            raise ConcurrencyRejected("client_concurrency_limit_exceeded")
        try:
            global_lock = self._acquire_slot("public-chat:global", self._global)
        except Exception:
            client_lock.release()
            raise
        if global_lock is None:
            client_lock.release()
            raise ConcurrencyRejected("global_concurrency_limit_exceeded")
        return _RedisLockLease((client_lock, global_lock))

    def _acquire_slot(self, namespace: str, count: int):
        try:
            for slot in range(count):
                lock = self._redis.lock(
                    f"{namespace}:{slot}",
                    timeout=self._lease_seconds,
                    blocking_timeout=0,
                    thread_local=False,
                )
                if lock.acquire(blocking=False):
                    return lock
        except RedisError as exc:
            raise RuntimeError("public_chat_unavailable") from exc
        return None


class TokenBudget:
    """Conservative byte-based estimator for models without a bundled tokenizer.

    UTF-8 byte count plus per-section overhead intentionally overestimates ordinary
    OpenAI text tokenisation, so provider context limits are never approached optimistically.
    """

    def __init__(
        self,
        *,
        max_input_tokens: int,
        max_context_tokens: int,
        max_context_chunks: int,
        model_context_tokens: int,
        output_tokens: int,
    ) -> None:
        self.max_input_tokens = max_input_tokens
        self.max_context_tokens = max_context_tokens
        self.max_context_chunks = max_context_chunks
        self.model_context_tokens = model_context_tokens
        self.output_tokens = output_tokens

    @staticmethod
    def estimate_text(value: str) -> int:
        return len(value.encode("utf-8")) + 4

    def select_context(self, contents: list[str]) -> tuple[str, ...]:
        selected: list[str] = []
        used = 0
        for content in contents[: self.max_context_chunks]:
            cost = self.estimate_text(content)
            if used + cost > self.max_context_tokens:
                continue
            selected.append(content)
            used += cost
        return tuple(selected)

    def validate_prompt(self, system_prompt: str, user_prompt: str) -> int:
        estimated = self.estimate_text(system_prompt) + self.estimate_text(user_prompt)
        if estimated > self.max_input_tokens:
            raise ValueError("input_token_limit_exceeded")
        if estimated + self.output_tokens > self.model_context_tokens:
            raise ValueError("input_token_limit_exceeded")
        return estimated


@dataclass(slots=True)
class PublicChatRequestPermit:
    identity: AnonymousClientIdentity
    concurrency: ConcurrencyLease

    def release(self) -> None:
        self.concurrency.release()


class PublicChatProtection:
    def __init__(
        self,
        settings: PublicAssistantChatSettings,
        resolver: AnonymousClientResolver,
        rate_limiter: PublicChatRateLimiter,
        concurrency_limiter: InMemoryConcurrencyLimiter | RedisLockConcurrencyLimiter,
    ) -> None:
        self.settings = settings
        self._resolver = resolver
        self._rate_limiter = rate_limiter
        self._concurrency = concurrency_limiter

    @classmethod
    def for_tests(cls, settings: PublicAssistantChatSettings) -> "PublicChatProtection":
        from limits.storage import MemoryStorage

        return cls(
            settings,
            AnonymousClientResolver(
                settings.trusted_proxy_networks, hash_secret=settings.client_key_hash_secret
            ),
            PublicChatRateLimiter(settings, storage=MemoryStorage()),
            InMemoryConcurrencyLimiter(
                per_client=settings.maximum_concurrent_requests_per_client,
                global_limit=settings.maximum_concurrent_requests_global,
            ),
        )

    def validate_http(self, *, origin: str | None, content_type: str | None) -> None:
        if origin is not None and origin not in self.settings.allowed_origins:
            raise PublicChatRejected(403, "origin_not_allowed", "Origin is not allowed.")
        media_type = (content_type or "").split(";", 1)[0].strip().lower()
        if media_type != "application/json":
            raise PublicChatRejected(
                415, "unsupported_media_type", "Content-Type must be application/json."
            )

    def validate_request(self, request: PublicChatRequest) -> None:
        settings = self.settings
        if len(request.message) > settings.maximum_message_characters:
            raise PublicChatRejected(422, "message_too_long", "The message is too long.")
        if len(request.history) > settings.maximum_history_messages:
            raise PublicChatRejected(
                422, "too_many_history_messages", "There are too many history messages."
            )
        if any(
            len(item.content) > settings.maximum_history_message_characters
            for item in request.history
        ):
            raise PublicChatRejected(422, "history_too_large", "The history is too large.")
        history_characters = sum(len(item.content) for item in request.history)
        history_tokens = sum(TokenBudget.estimate_text(item.content) for item in request.history)
        if (
            history_characters > settings.maximum_history_characters
            or history_tokens > settings.maximum_history_tokens
        ):
            raise PublicChatRejected(422, "history_too_large", "The history is too large.")

    def acquire(
        self,
        *,
        peer_ip: str | None,
        forwarded_for: str | None,
        anonymous_session: str | None,
    ) -> PublicChatRequestPermit:
        identity = self._resolver.resolve(
            peer_ip=peer_ip,
            forwarded_for=forwarded_for,
            anonymous_session=anonymous_session,
        )
        try:
            rate = self._rate_limiter.check(identity.client_key)
        except Exception as exc:
            raise PublicChatRejected(
                503, "public_chat_unavailable", "Public chat is temporarily unavailable."
            ) from exc
        if not rate.allowed:
            raise PublicChatRejected(
                429,
                "rate_limit_exceeded",
                "Too many requests.",
                retry_after_seconds=rate.retry_after_seconds,
                client_key_hash=identity.client_key,
            )
        try:
            concurrency = self._concurrency.acquire(identity.client_key)
        except ConcurrencyRejected as exc:
            code = str(exc)
            status = 429 if code == "client_concurrency_limit_exceeded" else 503
            raise PublicChatRejected(
                status, code, "Public chat is busy.", client_key_hash=identity.client_key
            ) from exc
        except Exception as exc:
            raise PublicChatRejected(
                503, "public_chat_unavailable", "Public chat is temporarily unavailable."
            ) from exc
        return PublicChatRequestPermit(identity, concurrency)


class PublicChatRejected(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        retry_after_seconds: int = 0,
        client_key_hash: str | None = None,
    ) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.retry_after_seconds = retry_after_seconds
        self.client_key_hash = client_key_hash
