from abc import ABC, abstractmethod
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from threading import RLock
from typing import Any
from uuid import UUID

from admin_auth.domain import (
    Administrator,
    AdministratorRole,
    AdministratorSession,
    AdministratorStatus,
)
from infrastructure.database.connection import get_connection


@dataclass(frozen=True)
class FailedLoginResult:
    administrator: Administrator | None
    newly_locked: bool = False


class AdministratorAuthRepository(ABC):
    @abstractmethod
    def has_any_administrator(self) -> bool: ...

    @abstractmethod
    def create_administrator_if_absent(self, administrator: Administrator) -> bool: ...

    @abstractmethod
    def get_administrator_by_email(self, email: str) -> Administrator | None: ...

    @abstractmethod
    def record_failed_login(
        self, email: str, now: datetime, threshold: int, lockout_seconds: int
    ) -> FailedLoginResult: ...

    @abstractmethod
    def complete_login(
        self,
        administrator: Administrator,
        session: AdministratorSession,
        now: datetime,
        replacement_password_hash: str | None,
    ) -> Administrator | None: ...

    @abstractmethod
    def get_session_principal(
        self, token_hash: str, now: datetime
    ) -> tuple[AdministratorSession, Administrator] | None: ...

    @abstractmethod
    def revoke_session(self, token_hash: str, now: datetime) -> UUID | None: ...

    @abstractmethod
    def cleanup_sessions(self, now: datetime, limit: int = 100) -> int: ...


class InMemoryAdministratorAuthRepository(AdministratorAuthRepository):
    def __init__(self) -> None:
        self._administrators: dict[UUID, Administrator] = {}
        self._sessions: dict[UUID, AdministratorSession] = {}
        self._lock = RLock()

    def create_administrator_if_absent(self, administrator: Administrator) -> bool:
        with self._lock:
            if any(item.email == administrator.email for item in self._administrators.values()):
                return False
            self._administrators[administrator.id] = deepcopy(administrator)
            return True

    def has_any_administrator(self) -> bool:
        with self._lock:
            return bool(self._administrators)

    def get_administrator_by_email(self, email: str) -> Administrator | None:
        with self._lock:
            found = next(
                (item for item in self._administrators.values() if item.email == email), None
            )
            return deepcopy(found)

    def record_failed_login(
        self, email: str, now: datetime, threshold: int, lockout_seconds: int
    ) -> FailedLoginResult:
        with self._lock:
            administrator = next(
                (item for item in self._administrators.values() if item.email == email), None
            )
            if administrator is None:
                return FailedLoginResult(None)
            prior_count = (
                0
                if administrator.locked_until and administrator.locked_until <= now
                else administrator.failed_login_count
            )
            count = prior_count + 1
            newly_locked = count >= threshold
            updated = replace(
                administrator,
                failed_login_count=count,
                locked_until=now + timedelta(seconds=lockout_seconds) if newly_locked else None,
                updated_at=now,
            )
            self._administrators[updated.id] = updated
            return FailedLoginResult(deepcopy(updated), newly_locked)

    def complete_login(
        self,
        administrator: Administrator,
        session: AdministratorSession,
        now: datetime,
        replacement_password_hash: str | None,
    ) -> Administrator | None:
        with self._lock:
            current = self._administrators.get(administrator.id)
            if (
                current is None
                or current.password_hash != administrator.password_hash
                or current.status is not AdministratorStatus.active
                or current.is_locked(now)
            ):
                return None
            updated = replace(
                current,
                password_hash=replacement_password_hash or current.password_hash,
                failed_login_count=0,
                locked_until=None,
                last_login_at=now,
                updated_at=now,
            )
            self._administrators[updated.id] = updated
            self._sessions[session.id] = deepcopy(session)
            return deepcopy(updated)

    def get_session_principal(
        self, token_hash: str, now: datetime
    ) -> tuple[AdministratorSession, Administrator] | None:
        with self._lock:
            session = next(
                (item for item in self._sessions.values() if item.token_hash == token_hash), None
            )
            if session is None or not session.authorizes(now):
                return None
            administrator = self._administrators.get(session.administrator_id)
            if administrator is None:
                return None
            return deepcopy(session), deepcopy(administrator)

    def revoke_session(self, token_hash: str, now: datetime) -> UUID | None:
        with self._lock:
            session = next(
                (item for item in self._sessions.values() if item.token_hash == token_hash), None
            )
            if session is None:
                return None
            if session.revoked_at is None:
                self._sessions[session.id] = replace(session, revoked_at=now)
            return session.id

    def cleanup_sessions(self, now: datetime, limit: int = 100) -> int:
        with self._lock:
            stale = [
                session_id
                for session_id, session in self._sessions.items()
                if session.expires_at <= now or session.revoked_at is not None
            ][:limit]
            for session_id in stale:
                del self._sessions[session_id]
            return len(stale)

    def set_administrator_status(self, administrator_id: UUID, status: AdministratorStatus) -> None:
        with self._lock:
            current = self._administrators[administrator_id]
            self._administrators[administrator_id] = replace(current, status=status)

    @property
    def sessions(self) -> tuple[AdministratorSession, ...]:
        with self._lock:
            return tuple(deepcopy(tuple(self._sessions.values())))


class PostgresAdministratorAuthRepository(AdministratorAuthRepository):
    def __init__(self, connection_factory: Callable[[], Any] = get_connection) -> None:
        self._connection_factory = connection_factory

    def create_administrator_if_absent(self, administrator: Administrator) -> bool:
        with self._connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO administrators (
                    id, email, password_hash, role, status, failed_login_count,
                    locked_until, last_login_at, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (email) DO NOTHING
                """,
                self._administrator_parameters(administrator),
            )
            return cursor.rowcount == 1

    def has_any_administrator(self) -> bool:
        with self._connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT EXISTS (SELECT 1 FROM administrators)")
            row = cursor.fetchone()
        return bool(row and row[0])

    def get_administrator_by_email(self, email: str) -> Administrator | None:
        with self._connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(f"{self._ADMIN_SELECT} WHERE email = %s", (email,))
            row = cursor.fetchone()
        return self._administrator_from_row(row) if row else None

    def record_failed_login(
        self, email: str, now: datetime, threshold: int, lockout_seconds: int
    ) -> FailedLoginResult:
        with self._connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                WITH current AS (
                    SELECT id,
                           CASE WHEN locked_until IS NOT NULL AND locked_until <= %(now)s
                                THEN 1 ELSE failed_login_count + 1 END AS next_count
                    FROM administrators WHERE email = %(email)s FOR UPDATE
                )
                UPDATE administrators AS administrators
                SET failed_login_count = current.next_count,
                    locked_until = CASE WHEN current.next_count >= %(threshold)s
                        THEN %(now)s + (%(lockout_seconds)s * INTERVAL '1 second') ELSE NULL END,
                    updated_at = %(now)s
                FROM current WHERE administrators.id = current.id
                RETURNING administrators.id, administrators.email, administrators.password_hash,
                    administrators.role, administrators.status, administrators.failed_login_count,
                    administrators.locked_until, administrators.last_login_at,
                    administrators.created_at, administrators.updated_at,
                    current.next_count >= %(threshold)s
                """,
                {
                    "email": email,
                    "now": now,
                    "threshold": threshold,
                    "lockout_seconds": lockout_seconds,
                },
            )
            row = cursor.fetchone()
        if row is None:
            return FailedLoginResult(None)
        return FailedLoginResult(self._administrator_from_row(row[:10]), bool(row[10]))

    def complete_login(
        self,
        administrator: Administrator,
        session: AdministratorSession,
        now: datetime,
        replacement_password_hash: str | None,
    ) -> Administrator | None:
        with self._connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""{self._ADMIN_SELECT} WHERE id = %s FOR UPDATE""",
                (str(administrator.id),),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            current = self._administrator_from_row(row)
            if (
                current.password_hash != administrator.password_hash
                or current.status is not AdministratorStatus.active
                or current.is_locked(now)
            ):
                return None
            cursor.execute(
                """
                UPDATE administrators
                SET password_hash = %s, failed_login_count = 0, locked_until = NULL,
                    last_login_at = %s, updated_at = %s
                WHERE id = %s
                """,
                (
                    replacement_password_hash or current.password_hash,
                    now,
                    now,
                    str(current.id),
                ),
            )
            cursor.execute(
                """
                INSERT INTO administrator_sessions (
                    id, administrator_id, token_hash, created_at, last_seen_at, expires_at, revoked_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    str(session.id),
                    str(session.administrator_id),
                    session.token_hash,
                    session.created_at,
                    session.last_seen_at,
                    session.expires_at,
                    session.revoked_at,
                ),
            )
            return Administrator(
                id=current.id,
                email=current.email,
                password_hash=replacement_password_hash or current.password_hash,
                role=current.role,
                status=current.status,
                failed_login_count=0,
                locked_until=None,
                last_login_at=now,
                created_at=current.created_at,
                updated_at=now,
            )

    def get_session_principal(
        self, token_hash: str, now: datetime
    ) -> tuple[AdministratorSession, Administrator] | None:
        with self._connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT s.id, s.administrator_id, s.token_hash, s.created_at, s.last_seen_at,
                       s.expires_at, s.revoked_at,
                       a.id, a.email, a.password_hash, a.role, a.status,
                       a.failed_login_count, a.locked_until, a.last_login_at,
                       a.created_at, a.updated_at
                FROM administrator_sessions AS s
                JOIN administrators AS a ON a.id = s.administrator_id
                WHERE s.token_hash = %s AND s.revoked_at IS NULL AND s.expires_at > %s
                """,
                (token_hash, now),
            )
            row = cursor.fetchone()
            if row is not None and row[4] <= now - timedelta(minutes=5):
                cursor.execute(
                    """UPDATE administrator_sessions SET last_seen_at = %s
                       WHERE id = %s AND last_seen_at <= %s""",
                    (now, str(row[0]), now - timedelta(minutes=5)),
                )
        if row is None:
            return None
        return self._session_from_row(row[:7]), self._administrator_from_row(row[7:])

    def revoke_session(self, token_hash: str, now: datetime) -> UUID | None:
        with self._connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """UPDATE administrator_sessions SET revoked_at = COALESCE(revoked_at, %s)
                   WHERE token_hash = %s RETURNING id""",
                (now, token_hash),
            )
            row = cursor.fetchone()
        return UUID(str(row[0])) if row else None

    def cleanup_sessions(self, now: datetime, limit: int = 100) -> int:
        with self._connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM administrator_sessions WHERE id IN (
                    SELECT id FROM administrator_sessions
                    WHERE expires_at <= %s OR revoked_at IS NOT NULL
                    ORDER BY expires_at LIMIT %s
                )
                """,
                (now, limit),
            )
            return cursor.rowcount

    _ADMIN_SELECT = """
        SELECT id, email, password_hash, role, status, failed_login_count,
               locked_until, last_login_at, created_at, updated_at
        FROM administrators
    """

    @staticmethod
    def _administrator_parameters(administrator: Administrator) -> tuple[Any, ...]:
        return (
            str(administrator.id),
            administrator.email,
            administrator.password_hash,
            administrator.role.value,
            administrator.status.value,
            administrator.failed_login_count,
            administrator.locked_until,
            administrator.last_login_at,
            administrator.created_at,
            administrator.updated_at,
        )

    @staticmethod
    def _administrator_from_row(row: tuple[Any, ...]) -> Administrator:
        return Administrator(
            id=UUID(str(row[0])),
            email=str(row[1]),
            password_hash=str(row[2]),
            role=AdministratorRole(row[3]),
            status=AdministratorStatus(row[4]),
            failed_login_count=int(row[5]),
            locked_until=row[6],
            last_login_at=row[7],
            created_at=row[8],
            updated_at=row[9],
        )

    @staticmethod
    def _session_from_row(row: tuple[Any, ...]) -> AdministratorSession:
        return AdministratorSession(
            id=UUID(str(row[0])),
            administrator_id=UUID(str(row[1])),
            token_hash=str(row[2]),
            created_at=row[3],
            last_seen_at=row[4],
            expires_at=row[5],
            revoked_at=row[6],
        )
