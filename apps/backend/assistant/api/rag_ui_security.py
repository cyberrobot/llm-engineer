from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends

from admin_auth.api_errors import admin_auth_error
from admin_auth.api_models import AdminAuthErrorCode
from admin_auth.dependencies import require_administrator_role
from admin_auth.domain import Administrator
from assistant.domain.rag_access import INTERNAL_ADMINISTRATOR_RAG_ACCESS_POLICY

RAG_UI_REQUEST_MAX_BYTES = 32_768


@dataclass(frozen=True, slots=True)
class RagRetrievalAuthorization:
    principal_id: str
    permitted_roles: tuple[str, ...]
    default_role: str


def require_rag_retrieval_authorization(
    administrator: Annotated[Administrator, Depends(require_administrator_role)],
) -> RagRetrievalAuthorization:
    policy = INTERNAL_ADMINISTRATOR_RAG_ACCESS_POLICY
    return RagRetrievalAuthorization(
        principal_id=str(administrator.id),
        permitted_roles=policy.permitted_roles,
        default_role=policy.default_role,
    )


def resolve_effective_rag_role(
    requested_role: str | None,
    authorization: RagRetrievalAuthorization,
) -> str:
    if not authorization.permitted_roles:
        raise admin_auth_error(AdminAuthErrorCode.forbidden)
    effective_role = requested_role or authorization.default_role
    if effective_role not in authorization.permitted_roles:
        raise admin_auth_error(AdminAuthErrorCode.forbidden)
    return effective_role
