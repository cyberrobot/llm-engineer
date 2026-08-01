import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from uuid import uuid4

from admin_auth.domain import (
    Administrator,
    AdministratorRole,
    AdministratorSession,
    AdministratorStatus,
    normalize_administrator_email,
)
from admin_auth.passwords import AdministratorPasswordService
from admin_auth.repository import AdministratorAuthRepository
from admin_auth.tokens import generate_session_token, hash_session_token
from core.metrics import administrator_authentication_metrics

logger = logging.getLogger(__name__)


class InvalidCredentials(Exception):
    pass


class AuthenticationRequired(Exception):
    pass


class PermissionDenied(Exception):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _email_log_identifier(email: str) -> str:
    return sha256(email.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class LoginResult:
    administrator: Administrator
    session_token: str
    expires_at: datetime


class AdministratorAuthenticationService:
    def __init__(
        self,
        repository: AdministratorAuthRepository,
        password_service: AdministratorPasswordService,
        *,
        session_ttl_seconds: int,
        login_max_failures: int,
        login_lockout_seconds: int,
        clock: Callable[[], datetime] = utc_now,
        token_factory: Callable[[], str] = generate_session_token,
    ) -> None:
        self._repository = repository
        self._passwords = password_service
        self._session_ttl_seconds = session_ttl_seconds
        self._login_max_failures = login_max_failures
        self._login_lockout_seconds = login_lockout_seconds
        self._clock = clock
        self._token_factory = token_factory

    def bootstrap(self, email: str, password: str) -> bool:
        normalized_email = normalize_administrator_email(email)
        password_hash = self._passwords.hash(password)
        now = self._clock()
        administrator = Administrator(
            id=uuid4(),
            email=normalized_email,
            password_hash=password_hash,
            role=AdministratorRole.administrator,
            status=AdministratorStatus.active,
            failed_login_count=0,
            locked_until=None,
            last_login_at=None,
            created_at=now,
            updated_at=now,
        )
        created = self._repository.create_administrator_if_absent(administrator)
        if created:
            logger.info(
                "admin_bootstrap_created",
                extra={"administrator_id": str(administrator.id)},
            )
            return True
        existing = self._repository.get_administrator_by_email(normalized_email)
        if existing is None or existing.role is not AdministratorRole.administrator:
            raise RuntimeError(
                "Configured administrator bootstrap identity conflicts with stored data."
            )
        return False

    def login(self, email: str, password: str) -> LoginResult:
        administrator_authentication_metrics.login_attempts.inc()
        normalized_email = normalize_administrator_email(email)
        now = self._clock()
        administrator = self._repository.get_administrator_by_email(normalized_email)
        if administrator is None:
            self._passwords.verify_dummy(password)
            self._log_login_failure(normalized_email, "unknown_identity")
            raise InvalidCredentials
        if administrator.status is not AdministratorStatus.active:
            self._passwords.verify_dummy(password)
            self._log_login_failure(normalized_email, "inactive_account")
            raise InvalidCredentials
        if administrator.is_locked(now):
            self._passwords.verify_dummy(password)
            self._log_login_failure(normalized_email, "temporary_lockout")
            raise InvalidCredentials
        if not self._passwords.verify(administrator.password_hash, password):
            failure = self._repository.record_failed_login(
                normalized_email,
                now,
                self._login_max_failures,
                self._login_lockout_seconds,
            )
            if failure.newly_locked and failure.administrator is not None:
                logger.warning(
                    "admin_account_locked",
                    extra={"administrator_id": str(failure.administrator.id)},
                )
            self._log_login_failure(normalized_email, "invalid_password")
            raise InvalidCredentials

        raw_token = self._token_factory()
        expires_at = now + timedelta(seconds=self._session_ttl_seconds)
        session = AdministratorSession(
            id=uuid4(),
            administrator_id=administrator.id,
            token_hash=hash_session_token(raw_token),
            created_at=now,
            last_seen_at=now,
            expires_at=expires_at,
        )
        replacement_hash = (
            self._passwords.hash(password)
            if self._passwords.needs_rehash(administrator.password_hash)
            else None
        )
        authenticated = self._repository.complete_login(
            administrator, session, now, replacement_hash
        )
        if authenticated is None:
            self._passwords.verify_dummy(password)
            self._log_login_failure(normalized_email, "concurrent_state_change")
            raise InvalidCredentials
        self._repository.cleanup_sessions(now)
        logger.info(
            "admin_login_succeeded",
            extra={
                "administrator_id": str(authenticated.id),
                "session_id": str(session.id),
            },
        )
        administrator_authentication_metrics.login_successes.inc()
        administrator_authentication_metrics.sessions_created.inc()
        return LoginResult(authenticated, raw_token, expires_at)

    def authenticate(self, raw_token: str | None) -> tuple[AdministratorSession, Administrator]:
        if not raw_token:
            raise AuthenticationRequired
        now = self._clock()
        principal = self._repository.get_session_principal(hash_session_token(raw_token), now)
        if principal is None:
            logger.warning("admin_session_rejected", extra={"reason": "invalid_session"})
            raise AuthenticationRequired
        session, administrator = principal
        if administrator.status is not AdministratorStatus.active:
            logger.warning(
                "admin_session_rejected",
                extra={"session_id": str(session.id), "reason": "inactive_account"},
            )
            raise AuthenticationRequired
        return session, administrator

    def require_role(self, administrator: Administrator, role: AdministratorRole) -> Administrator:
        if administrator.role is not role:
            raise PermissionDenied
        return administrator

    def logout(self, raw_token: str | None) -> None:
        if not raw_token:
            return
        session_id = self._repository.revoke_session(hash_session_token(raw_token), self._clock())
        logger.info(
            "admin_logout",
            extra={"session_id": str(session_id) if session_id else None},
        )
        if session_id is not None:
            administrator_authentication_metrics.sessions_revoked.inc()

    @staticmethod
    def _log_login_failure(email: str, reason: str) -> None:
        administrator_authentication_metrics.login_failures.inc()
        logger.warning(
            "admin_login_failed",
            extra={"email_hash": _email_log_identifier(email), "reason": reason},
        )
