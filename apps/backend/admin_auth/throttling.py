import math
import time
from dataclasses import dataclass
from hashlib import sha256

from limits import RateLimitItemPerSecond
from limits.storage import Storage, storage_from_string
from limits.strategies import FixedWindowRateLimiter


@dataclass(frozen=True)
class LoginThrottleDecision:
    allowed: bool
    retry_after_seconds: int = 0


class LoginThrottle:
    """Layered fixed-window throttling using the project's established limits library."""

    def __init__(
        self,
        storage_uri: str,
        *,
        window_seconds: int,
        ip_attempts: int,
        email_attempts: int,
        global_attempts: int,
        enabled: bool = True,
        storage: Storage | None = None,
    ) -> None:
        self._enabled = enabled
        self._limiter = FixedWindowRateLimiter(storage or storage_from_string(storage_uri))
        self._rules = (
            (RateLimitItemPerSecond(ip_attempts, window_seconds), "ip"),
            (RateLimitItemPerSecond(email_attempts, window_seconds), "email"),
            (RateLimitItemPerSecond(global_attempts, window_seconds), "global"),
        )

    def check(self, source_ip: str, normalized_email: str) -> LoginThrottleDecision:
        if not self._enabled:
            return LoginThrottleDecision(True)
        email_key = sha256(normalized_email.encode("utf-8")).hexdigest()
        identifiers = {"ip": source_ip, "email": email_key, "global": "all"}
        retry_after = 0
        allowed = True
        for rule, category in self._rules:
            identifier = identifiers[category]
            if not self._limiter.hit(rule, category, identifier):
                allowed = False
                window = self._limiter.get_window_stats(rule, category, identifier)
                retry_after = max(retry_after, max(1, math.ceil(window.reset_time - time.time())))
        return LoginThrottleDecision(allowed, retry_after)
