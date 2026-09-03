import pytest

from assistant.domain.rag_access import (
    DEFAULT_INTERNAL_RAG_DOCUMENT_ROLE,
    INTERNAL_ADMINISTRATOR_RAG_ACCESS_POLICY,
    LEGACY_RAG_DOCUMENT_ROLES,
    RagAccessPolicy,
)


def test_internal_administrator_policy_preserves_legacy_document_roles():
    assert INTERNAL_ADMINISTRATOR_RAG_ACCESS_POLICY.permitted_roles == (
        "doctor",
        "nurse",
        "analyst",
        "manager",
        "agent",
    )
    assert INTERNAL_ADMINISTRATOR_RAG_ACCESS_POLICY.default_role == "doctor"
    assert DEFAULT_INTERNAL_RAG_DOCUMENT_ROLE in LEGACY_RAG_DOCUMENT_ROLES
    assert "administrator" not in LEGACY_RAG_DOCUMENT_ROLES


def test_rag_access_policy_requires_a_permitted_default():
    with pytest.raises(ValueError, match="permitted default role"):
        RagAccessPolicy(permitted_roles=("doctor",), default_role="manager")
