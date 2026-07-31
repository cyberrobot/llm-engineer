from dataclasses import dataclass
from secrets import compare_digest


@dataclass(frozen=True)
class ApiPrincipal:
    """Authenticated API caller identity derived from trusted server configuration."""

    identifier: str
    permissions: frozenset[str]

    def __post_init__(self) -> None:
        if not self.identifier.strip():
            raise ValueError("An API principal requires an identifier.")
        if any(not permission.strip() for permission in self.permissions):
            raise ValueError("API principal permissions must not be empty.")


@dataclass(frozen=True)
class ApiKeyCredential:
    api_key: str
    principal: ApiPrincipal

    def __post_init__(self) -> None:
        if not self.api_key:
            raise ValueError("An API-key credential requires a key.")


def authenticate_api_key(
    presented_api_key: str | None,
    credentials: tuple[ApiKeyCredential, ...],
) -> ApiPrincipal | None:
    """Resolve an opaque key without exposing it or accepting partial matches."""

    if not presented_api_key:
        return None
    for credential in credentials:
        if compare_digest(presented_api_key, credential.api_key):
            return credential.principal
    return None
