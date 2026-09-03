from pathlib import Path

ROLE_SQL = (
    Path(__file__).parents[1] / "infrastructure" / "database" / "rag_read_role.sql"
).read_text(encoding="utf-8")


def test_rag_read_role_sql_defines_only_the_required_read_privileges():
    normalized = " ".join(ROLE_SQL.upper().split())

    assert "NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE INHERIT" in normalized
    assert "NOINHERIT" not in normalized
    assert "NOREPLICATION NOBYPASSRLS" in normalized
    assert "GRANT CONNECT ON DATABASE" in normalized
    assert "GRANT USAGE ON SCHEMA PUBLIC TO RAG_READER" in normalized
    assert "GRANT SELECT ON TABLE PUBLIC.DOCUMENTS, PUBLIC.CHUNKS TO RAG_READER" in normalized
    assert "REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA PUBLIC FROM RAG_READER" in normalized
    assert "REVOKE CREATE ON SCHEMA PUBLIC FROM RAG_READER" in normalized
    for forbidden_grant in ("INSERT", "UPDATE", "DELETE", "TRUNCATE", "CREATE"):
        assert f"GRANT {forbidden_grant}" not in normalized
    assert "PASSWORD" not in normalized
