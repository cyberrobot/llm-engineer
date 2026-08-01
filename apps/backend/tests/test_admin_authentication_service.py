from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from admin_auth.domain import AdministratorRole, AdministratorStatus
from admin_auth.passwords import AdministratorPasswordService
from admin_auth.repository import InMemoryAdministratorAuthRepository
from admin_auth.service import (
    AdministratorAuthenticationService,
    AuthenticationRequired,
    InvalidCredentials,
    PermissionDenied,
)
from admin_auth.tokens import hash_session_token

PASSWORD = "correct horse battery staple"


class MutableClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 8, 1, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now


def build_service(max_failures: int = 3):
    repository = InMemoryAdministratorAuthRepository()
    passwords = AdministratorPasswordService()
    clock = MutableClock()
    service = AdministratorAuthenticationService(
        repository,
        passwords,
        session_ttl_seconds=3600,
        login_max_failures=max_failures,
        login_lockout_seconds=300,
        clock=clock,
        token_factory=lambda: "opaque-test-session-token",
    )
    return service, repository, passwords, clock


def test_bootstrap_is_normalized_idempotent_and_preserves_existing_password():
    service, repository, _passwords, _clock = build_service()

    assert service.bootstrap(" Admin@Example.COM ", PASSWORD) is True
    first = repository.get_administrator_by_email("admin@example.com")
    assert service.bootstrap("admin@example.com", "different secure password") is False
    preserved = repository.get_administrator_by_email("admin@example.com")

    assert first is not None and preserved is not None
    assert first.password_hash == preserved.password_hash
    assert PASSWORD not in preserved.password_hash


def test_login_creates_only_hashed_session_and_restores_identity():
    service, repository, _passwords, _clock = build_service()
    service.bootstrap("admin@example.com", PASSWORD)

    result = service.login(" ADMIN@example.com ", PASSWORD)
    sessions = repository.sessions

    assert result.administrator.email == "admin@example.com"
    assert result.administrator.failed_login_count == 0
    assert len(sessions) == 1
    assert sessions[0].token_hash == hash_session_token(result.session_token)
    assert result.session_token not in repr(sessions[0])
    _session, current = service.authenticate(result.session_token)
    assert current.id == result.administrator.id


def test_wrong_passwords_lock_temporarily_and_success_after_expiry_resets_failures():
    service, repository, _passwords, clock = build_service(max_failures=2)
    service.bootstrap("admin@example.com", PASSWORD)

    for _ in range(2):
        with pytest.raises(InvalidCredentials):
            service.login("admin@example.com", "wrong-password")
    locked = repository.get_administrator_by_email("admin@example.com")
    assert locked is not None
    assert locked.failed_login_count == 2
    assert locked.locked_until == clock.now + timedelta(minutes=5)
    with pytest.raises(InvalidCredentials):
        service.login("admin@example.com", PASSWORD)

    clock.now += timedelta(minutes=5)
    result = service.login("admin@example.com", PASSWORD)
    assert result.administrator.failed_login_count == 0
    assert result.administrator.locked_until is None


@pytest.mark.parametrize("email", ["unknown@example.com", "admin@example.com"])
def test_unknown_disabled_and_invalid_credentials_share_the_same_failure(email):
    service, repository, _passwords, _clock = build_service()
    service.bootstrap("admin@example.com", PASSWORD)
    if email == "admin@example.com":
        administrator = repository.get_administrator_by_email(email)
        assert administrator is not None
        repository.set_administrator_status(administrator.id, AdministratorStatus.disabled)

    with pytest.raises(InvalidCredentials):
        service.login(email, PASSWORD)


def test_expired_revoked_and_disabled_sessions_do_not_authorize():
    service, repository, _passwords, clock = build_service()
    service.bootstrap("admin@example.com", PASSWORD)
    first = service.login("admin@example.com", PASSWORD)
    service.logout(first.session_token)
    with pytest.raises(AuthenticationRequired):
        service.authenticate(first.session_token)

    second = service.login("admin@example.com", PASSWORD)
    administrator = repository.get_administrator_by_email("admin@example.com")
    assert administrator is not None
    repository.set_administrator_status(administrator.id, AdministratorStatus.disabled)
    with pytest.raises(AuthenticationRequired):
        service.authenticate(second.session_token)

    repository.set_administrator_status(administrator.id, AdministratorStatus.active)
    clock.now += timedelta(hours=1)
    with pytest.raises(AuthenticationRequired):
        service.authenticate(second.session_token)


def test_role_enforcement_uses_403_style_permission_failure():
    service, _repository, _passwords, _clock = build_service()
    with pytest.raises(PermissionDenied):
        service.require_role(SimpleNamespace(role="viewer"), AdministratorRole.administrator)
