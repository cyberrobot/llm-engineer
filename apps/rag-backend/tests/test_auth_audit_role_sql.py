from pathlib import Path


def test_auth_audit_role_grants_only_required_database_access():
    sql = (Path(__file__).parents[1] / "auth_audit_role.sql").read_text().upper()

    assert "GRANT SELECT (ADMINISTRATOR_ID, TOKEN_HASH, REVOKED_AT, EXPIRES_AT)" in sql
    assert "ON TABLE PUBLIC.ADMINISTRATOR_SESSIONS" in sql
    assert "GRANT SELECT (ID, ROLE, STATUS) ON TABLE PUBLIC.ADMINISTRATORS" in sql
    assert "GRANT SELECT, INSERT ON TABLE RAG.AUDIT_LOGS" in sql
    assert "GRANT USAGE, SELECT ON SEQUENCE RAG.AUDIT_LOGS_ID_SEQ" in sql
    assert "GRANT SELECT (SINGLETON, MAINTENANCE_ENABLED)" in sql
    assert "ON TABLE PUBLIC.OPERATIONS_RUNTIME_STATE" in sql
    assert "REVOKE CREATE ON SCHEMA PUBLIC" in sql
    assert "REVOKE CREATE ON SCHEMA RAG" in sql
    assert "SET ROLE RAG_MIGRATOR" in sql
    assert "RESET ROLE" in sql
    assert "CREATE ROLE RAG_AUTH_AUDIT" not in sql
    assert "RAG_AUTH_AUDIT MUST BE PROVISIONED BY THE CLUSTER ROLE ADMINISTRATOR" in sql
    for forbidden in ("UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"):
        assert f"GRANT {forbidden}" not in sql
    for table in ("DOCUMENTS", "CHUNKS", "DOCUMENT_INGESTION_JOBS"):
        assert f"GRANT SELECT ON TABLE PUBLIC.{table}" not in sql
        assert f"GRANT INSERT ON TABLE PUBLIC.{table}" not in sql


def test_migration_owner_requires_preprovisioning_and_is_scoped_to_rag_schema():
    sql = (Path(__file__).parents[1] / "migration_owner_role.sql").read_text().upper()

    assert "CREATE ROLE RAG_MIGRATOR" not in sql
    assert "RAG_MIGRATOR MUST BE PROVISIONED BY THE CLUSTER ROLE ADMINISTRATOR" in sql
    assert "CREATE SCHEMA IF NOT EXISTS RAG AUTHORIZATION RAG_MIGRATOR" in sql
    assert "ALTER SCHEMA RAG OWNER TO RAG_MIGRATOR" in sql
    assert "GRANT USAGE, CREATE ON SCHEMA RAG TO RAG_MIGRATOR" in sql
    assert "REVOKE CREATE ON SCHEMA PUBLIC FROM RAG_MIGRATOR" in sql
    assert "GRANT CONNECT ON DATABASE %I TO RAG_MIGRATOR" in sql
    assert "GRANT CREATE ON DATABASE" not in sql


def test_cluster_roles_are_no_login_and_have_no_elevated_capabilities():
    sql = (Path(__file__).parents[1] / "cluster_roles.sql").read_text().upper()

    for role in ("RAG_READER", "RAG_MIGRATOR", "RAG_AUTH_AUDIT"):
        assert role in sql
    assert "NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE" in sql
    assert "NOREPLICATION NOBYPASSRLS" in sql
