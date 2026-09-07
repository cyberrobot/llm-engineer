-- Run as the database/bootstrap owner after RAG migrations. The bootstrap owner
-- must first apply migration_owner_role.sql, which makes it a member of the
-- rag_migrator object-owner role. Deployments should
-- grant this NOLOGIN group role to the LOGIN role used by
-- RAG_AUTH_AUDIT_DATABASE_URL.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rag_auth_audit') THEN
        CREATE ROLE rag_auth_audit
            NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE INHERIT
            NOREPLICATION NOBYPASSRLS;
    ELSIF EXISTS (
        SELECT 1 FROM pg_roles
        WHERE rolname = 'rag_auth_audit'
          AND (
              rolcanlogin OR rolsuper OR rolcreatedb OR rolcreaterole
              OR rolreplication OR rolbypassrls
          )
    ) THEN
        RAISE EXCEPTION 'rag_auth_audit has forbidden elevated attributes';
    END IF;
END
$$;

DO $$
BEGIN
    EXECUTE format('REVOKE ALL PRIVILEGES ON DATABASE %I FROM rag_auth_audit', current_database());
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO rag_auth_audit', current_database());
END
$$;

REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM rag_auth_audit;
REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM rag_auth_audit;
REVOKE CREATE ON SCHEMA public FROM rag_auth_audit;
GRANT USAGE ON SCHEMA public TO rag_auth_audit;
GRANT SELECT (administrator_id, token_hash, revoked_at, expires_at)
    ON TABLE public.administrator_sessions TO rag_auth_audit;
GRANT SELECT (id, role, status) ON TABLE public.administrators TO rag_auth_audit;
GRANT SELECT (singleton, maintenance_enabled)
    ON TABLE public.operations_runtime_state TO rag_auth_audit;

SET ROLE rag_migrator;
REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA rag FROM rag_auth_audit;
REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA rag FROM rag_auth_audit;
REVOKE CREATE ON SCHEMA rag FROM rag_auth_audit;
GRANT USAGE ON SCHEMA rag TO rag_auth_audit;
GRANT SELECT, INSERT ON TABLE rag.audit_logs TO rag_auth_audit;
GRANT USAGE, SELECT ON SEQUENCE rag.audit_logs_id_seq TO rag_auth_audit;
RESET ROLE;
