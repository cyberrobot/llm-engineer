from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from datetime import datetime, timezone
from uuid import uuid4

import psycopg
import pytest

from admin_auth.passwords import AdministratorPasswordService
from admin_auth.repository import PostgresAdministratorAuthRepository
from admin_auth.service import (
    AdministratorAuthenticationService,
    AuthenticationRequired,
    InvalidCredentials,
)
from core.config import DATABASE_URL
from infrastructure.database.connection import get_connection, init_db

PASSWORD = "correct horse battery staple"


def require_database() -> None:
    if not DATABASE_URL:
        pytest.skip("DATABASE_URL is not configured")
    try:
        with psycopg.connect(DATABASE_URL, connect_timeout=2) as connection:
            connection.execute("SELECT 1")
    except psycopg.OperationalError as exc:
        pytest.skip(f"PostgreSQL test database is unavailable: {exc}")


def service() -> AdministratorAuthenticationService:
    return AdministratorAuthenticationService(
        PostgresAdministratorAuthRepository(),
        AdministratorPasswordService(),
        session_ttl_seconds=3600,
        login_max_failures=5,
        login_lockout_seconds=300,
        clock=lambda: datetime(2026, 8, 1, tzinfo=timezone.utc),
    )


def cleanup(email: str) -> None:
    with suppress(Exception), get_connection() as connection:
        connection.execute(
            """DELETE FROM administrator_sessions WHERE administrator_id IN
               (SELECT id FROM administrators WHERE email = %s)""",
            (email,),
        )
        connection.execute("DELETE FROM administrators WHERE email = %s", (email,))


def test_postgres_bootstrap_login_restore_logout_and_raw_token_non_persistence():
    require_database()
    init_db()
    email = f"admin-{uuid4().hex}@example.com"
    authentication = service()
    try:
        assert authentication.bootstrap(email, PASSWORD) is True
        assert authentication.bootstrap(email.upper(), "different secure password") is False

        login = authentication.login(email, PASSWORD)
        session, administrator = authentication.authenticate(login.session_token)
        assert administrator.email == email
        assert session.token_hash != login.session_token
        with get_connection() as connection:
            stored = connection.execute(
                "SELECT token_hash FROM administrator_sessions WHERE id = %s",
                (str(session.id),),
            ).fetchone()[0]
        assert stored == session.token_hash

        authentication.logout(login.session_token)
        with pytest.raises(AuthenticationRequired):
            authentication.authenticate(login.session_token)
    finally:
        cleanup(email)


def test_concurrent_failed_logins_atomically_reach_lockout_threshold():
    require_database()
    init_db()
    email = f"admin-{uuid4().hex}@example.com"
    authentication = service()
    authentication.bootstrap(email, PASSWORD)

    def fail_login(_attempt: int) -> None:
        with pytest.raises(InvalidCredentials):
            service().login(email, "wrong-password")

    try:
        with ThreadPoolExecutor(max_workers=5) as executor:
            list(executor.map(fail_login, range(5)))
        stored = PostgresAdministratorAuthRepository().get_administrator_by_email(email)
        assert stored is not None
        assert stored.failed_login_count == 5
        assert stored.locked_until == datetime(2026, 8, 1, 0, 5, tzinfo=timezone.utc)
    finally:
        cleanup(email)
