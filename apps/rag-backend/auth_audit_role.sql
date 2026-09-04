-- Run as the database owner after application migrations. Deployments should
-- grant this NOLOGIN group role to the LOGIN role used by
-- RAG_AUTH_AUDIT_DATABASE_URL.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rag_auth_audit') THEN
        CREATE ROLE rag_auth_audit
            NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE INHERIT
            NOREPLICATION NOBYPASSRLS;
    ELSE
        ALTER ROLE rag_auth_audit
            NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE INHERIT
            NOREPLICATION NOBYPASSRLS;
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
GRANT SELECT ON TABLE public.administrator_sessions, public.administrators TO rag_auth_audit;
GRANT SELECT, INSERT ON TABLE public.audit_logs TO rag_auth_audit;
GRANT USAGE, SELECT ON SEQUENCE public.audit_logs_id_seq TO rag_auth_audit;
