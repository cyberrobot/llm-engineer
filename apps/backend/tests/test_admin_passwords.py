import pytest

from admin_auth.passwords import (
    MAXIMUM_PASSWORD_LENGTH,
    AdministratorPasswordService,
    PasswordPolicyError,
)


def test_argon2id_hashes_verify_use_unique_salts_and_are_not_plaintext():
    service = AdministratorPasswordService()
    password = "correct horse battery staple"

    first = service.hash(password)
    second = service.hash(password)

    assert first.startswith("$argon2id$")
    assert first != second
    assert password not in first
    assert service.verify(first, password) is True
    assert service.verify(first, "incorrect-password") is False


@pytest.mark.parametrize("password", ["", "   ", "too-short"])
def test_new_password_policy_rejects_empty_whitespace_and_short_values(password):
    with pytest.raises(PasswordPolicyError):
        AdministratorPasswordService().hash(password)


def test_password_service_rejects_oversized_input_without_hashing_it():
    service = AdministratorPasswordService()
    oversized = "x" * (MAXIMUM_PASSWORD_LENGTH + 1)
    with pytest.raises(PasswordPolicyError, match="at most"):
        service.hash(oversized)
    assert service.verify(service.hash("valid-password-value"), oversized) is False


def test_dummy_verification_path_uses_a_valid_hash_and_rehash_detection_is_supported():
    service = AdministratorPasswordService()
    password_hash = service.hash("valid-password-value")

    assert service.verify_dummy("unknown-password") is False
    assert service.needs_rehash(password_hash) is False
