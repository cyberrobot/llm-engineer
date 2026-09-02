from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from admin_auth.domain import (
    Administrator,
    AdministratorRole,
    AdministratorSession,
    AdministratorStatus,
    normalize_administrator_email,
)
from admin_auth.repository import InMemoryAdministratorAuthRepository

NOW = datetime(2026, 8, 1, tzinfo=timezone.utc)


def administrator(email: str = "admin@example.com") -> Administrator:
    return Administrator(
        id=uuid4(),
        email=email,
        password_hash="argon2-hash",
        role=AdministratorRole.administrator,
        status=AdministratorStatus.active,
        failed_login_count=0,
        locked_until=None,
        last_login_at=None,
        created_at=NOW,
        updated_at=NOW,
    )


def test_administrator_email_is_normalized_and_validated():
    assert normalize_administrator_email("  Admin@Example.COM ") == "admin@example.com"
    with pytest.raises(ValueError, match="invalid"):
        normalize_administrator_email("not-an-email")
    with pytest.raises(ValueError, match="normalized"):
        administrator("Admin@example.com")


def test_repository_enforces_unique_normalized_email_identity():
    repository = InMemoryAdministratorAuthRepository()
    first = administrator()

    assert repository.create_administrator_if_absent(first) is True
    assert repository.create_administrator_if_absent(administrator()) is False
    assert repository.get_administrator_by_email("admin@example.com") == first


def test_domain_rejects_invalid_role_status_and_lockout_state():
    with pytest.raises(ValueError, match="role"):
        replace(administrator(), role="owner")
    with pytest.raises(ValueError, match="status"):
        replace(administrator(), status="pending")
    with pytest.raises(ValueError, match="Failed login"):
        replace(administrator(), failed_login_count=-1)


def test_authenticated_administrator_role_is_the_document_access_source_of_truth():
    principal = administrator()

    assert principal.document_access_roles == (AdministratorRole.administrator.value,)


def test_session_rejects_expiry_and_reports_revocation():
    session = AdministratorSession(
        id=uuid4(),
        administrator_id=uuid4(),
        token_hash="a" * 64,
        created_at=NOW,
        last_seen_at=NOW,
        expires_at=NOW + timedelta(hours=1),
    )
    assert session.authorizes(NOW) is True
    assert session.authorizes(NOW + timedelta(hours=1)) is False
    with pytest.raises(ValueError, match="timestamps"):
        AdministratorSession(
            id=uuid4(),
            administrator_id=uuid4(),
            token_hash="b" * 64,
            created_at=NOW,
            last_seen_at=NOW,
            expires_at=NOW,
        )
