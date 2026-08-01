from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from argon2.low_level import Type

MINIMUM_PASSWORD_LENGTH = 12
MAXIMUM_PASSWORD_LENGTH = 1024


class PasswordPolicyError(ValueError):
    pass


class AdministratorPasswordService:
    """Argon2id password storage with one central, upgradeable parameter set."""

    def __init__(self, hasher: PasswordHasher | None = None) -> None:
        self._hasher = hasher or PasswordHasher(type=Type.ID)
        self._dummy_hash = self._hasher.hash("dummy-administrator-password-only")

    def validate_new_password(self, password: str) -> None:
        if not password or not password.strip():
            raise PasswordPolicyError("Administrator password must not be empty.")
        if len(password) < MINIMUM_PASSWORD_LENGTH:
            raise PasswordPolicyError(
                f"Administrator password must be at least {MINIMUM_PASSWORD_LENGTH} characters."
            )
        if len(password) > MAXIMUM_PASSWORD_LENGTH:
            raise PasswordPolicyError(
                f"Administrator password must be at most {MAXIMUM_PASSWORD_LENGTH} characters."
            )

    def hash(self, password: str) -> str:
        self.validate_new_password(password)
        return self._hasher.hash(password)

    def verify(self, password_hash: str, password: str) -> bool:
        if len(password) > MAXIMUM_PASSWORD_LENGTH:
            return False
        try:
            return self._hasher.verify(password_hash, password)
        except (VerificationError, InvalidHashError):
            return False

    def verify_dummy(self, password: str) -> bool:
        return self.verify(self._dummy_hash, password)

    def needs_rehash(self, password_hash: str) -> bool:
        try:
            return self._hasher.check_needs_rehash(password_hash)
        except InvalidHashError:
            return False
