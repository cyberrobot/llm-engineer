from limits.storage import MemoryStorage

from admin_auth.throttling import LoginThrottle


def throttle(*, ip: int = 2, email: int = 2, global_limit: int = 20) -> LoginThrottle:
    return LoginThrottle(
        "memory://",
        window_seconds=60,
        ip_attempts=ip,
        email_attempts=email,
        global_attempts=global_limit,
        storage=MemoryStorage(),
    )


def test_login_throttle_enforces_ip_email_and_global_boundaries_with_retry_after():
    per_ip = throttle(ip=1, email=20)
    assert per_ip.check("192.0.2.1", "one@example.com").allowed is True
    rejected = per_ip.check("192.0.2.1", "two@example.com")
    assert rejected.allowed is False and rejected.retry_after_seconds > 0

    per_email = throttle(ip=20, email=1)
    assert per_email.check("192.0.2.1", "admin@example.com").allowed is True
    assert per_email.check("192.0.2.2", "admin@example.com").allowed is False

    global_boundary = throttle(ip=20, email=20, global_limit=1)
    assert global_boundary.check("192.0.2.1", "one@example.com").allowed is True
    assert global_boundary.check("192.0.2.2", "two@example.com").allowed is False


def test_disabled_throttle_deliberately_allows_test_requests():
    value = LoginThrottle(
        "memory://",
        window_seconds=60,
        ip_attempts=1,
        email_attempts=1,
        global_attempts=1,
        enabled=False,
        storage=MemoryStorage(),
    )
    assert value.check("192.0.2.1", "admin@example.com").allowed is True
    assert value.check("192.0.2.1", "admin@example.com").allowed is True
