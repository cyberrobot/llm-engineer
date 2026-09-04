from pathlib import Path


def test_auth_audit_role_grants_only_required_database_access():
    sql = (Path(__file__).parents[1] / "auth_audit_role.sql").read_text().upper()

    assert "GRANT SELECT (ADMINISTRATOR_ID, TOKEN_HASH, REVOKED_AT, EXPIRES_AT)" in sql
    assert "ON TABLE PUBLIC.ADMINISTRATOR_SESSIONS" in sql
    assert "GRANT SELECT (ID, ROLE, STATUS) ON TABLE PUBLIC.ADMINISTRATORS" in sql
    assert "GRANT SELECT, INSERT ON TABLE PUBLIC.AUDIT_LOGS" in sql
    assert "GRANT USAGE, SELECT ON SEQUENCE PUBLIC.AUDIT_LOGS_ID_SEQ" in sql
    assert "REVOKE CREATE ON SCHEMA PUBLIC" in sql
    for forbidden in ("UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"):
        assert f"GRANT {forbidden}" not in sql
    for table in ("DOCUMENTS", "CHUNKS", "DOCUMENT_INGESTION_JOBS"):
        assert f"GRANT SELECT ON TABLE PUBLIC.{table}" not in sql
        assert f"GRANT INSERT ON TABLE PUBLIC.{table}" not in sql
