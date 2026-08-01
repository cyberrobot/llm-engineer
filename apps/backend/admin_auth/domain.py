from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from uuid import UUID

from email_validator import EmailNotValidError, validate_email


class AdministratorRole(str, Enum):
    administrator = "administrator"


class AdministratorStatus(str, Enum):
    active = "active"
    disabled = "disabled"


def normalize_administrator_email(value: str) -> str:
    candidate = value.strip().lower()
    if len(candidate) > 254:
        raise ValueError("Administrator email is too long.")
    try:
        return validate_email(candidate, check_deliverability=False).normalized.lower()
    except EmailNotValidError as exc:
        raise ValueError("Administrator email is invalid.") from exc


def _require_aware(value: datetime, field: str) -> None:
    if value.tzinfo is None:
        raise ValueError(f"{field} must include a timezone.")


@dataclass(frozen=True, slots=True)
class Administrator:
    id: UUID
    email: str
    password_hash: str
    role: AdministratorRole
    status: AdministratorStatus
    failed_login_count: int
    locked_until: datetime | None
    last_login_at: datetime | None
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        if self.id.int == 0:
            raise ValueError("Administrator ID must not be nil.")
        if self.email != normalize_administrator_email(self.email):
            raise ValueError("Administrator email must be normalized.")
        if not self.password_hash:
            raise ValueError("Administrator password hash must not be empty.")
        if not isinstance(self.role, AdministratorRole):
            raise ValueError("Administrator role is invalid.")
        if not isinstance(self.status, AdministratorStatus):
            raise ValueError("Administrator status is invalid.")
        if self.failed_login_count < 0:
            raise ValueError("Failed login count must not be negative.")
        for field, value in (
            ("locked_until", self.locked_until),
            ("last_login_at", self.last_login_at),
            ("created_at", self.created_at),
            ("updated_at", self.updated_at),
        ):
            if value is not None:
                _require_aware(value, field)
        if self.updated_at < self.created_at:
            raise ValueError("Administrator update timestamp cannot precede creation.")

    def is_locked(self, now: datetime) -> bool:
        _require_aware(now, "now")
        return self.locked_until is not None and self.locked_until > now


@dataclass(frozen=True, slots=True)
class AdministratorSession:
    id: UUID
    administrator_id: UUID
    token_hash: str
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.id.int == 0 or self.administrator_id.int == 0:
            raise ValueError("Session identifiers must not be nil.")
        if len(self.token_hash) != 64:
            raise ValueError("Session token hash must be a SHA-256 hex digest.")
        for field, value in (
            ("created_at", self.created_at),
            ("last_seen_at", self.last_seen_at),
            ("expires_at", self.expires_at),
            ("revoked_at", self.revoked_at),
        ):
            if value is not None:
                _require_aware(value, field)
        if self.last_seen_at < self.created_at or self.expires_at <= self.created_at:
            raise ValueError("Administrator session timestamps are inconsistent.")

    def authorizes(self, now: datetime) -> bool:
        return self.revoked_at is None and self.expires_at > now
