from dataclasses import dataclass

LEGACY_RAG_DOCUMENT_ROLES = ("doctor", "nurse", "analyst", "manager", "agent")
DEFAULT_INTERNAL_RAG_DOCUMENT_ROLE = "doctor"


@dataclass(frozen=True, slots=True)
class RagAccessPolicy:
    """Server-owned document roles available to a protected RAG experience."""

    permitted_roles: tuple[str, ...]
    default_role: str

    def __post_init__(self) -> None:
        if not self.permitted_roles or self.default_role not in self.permitted_roles:
            raise ValueError("RAG access policy requires a permitted default role.")


# The legacy RAG UI is an internal administrator debugging surface. Administrator
# authentication grants inspection of its established document-role vocabulary;
# it does not turn the administrator application role into a document role.
INTERNAL_ADMINISTRATOR_RAG_ACCESS_POLICY = RagAccessPolicy(
    permitted_roles=LEGACY_RAG_DOCUMENT_ROLES,
    default_role=DEFAULT_INTERNAL_RAG_DOCUMENT_ROLE,
)
