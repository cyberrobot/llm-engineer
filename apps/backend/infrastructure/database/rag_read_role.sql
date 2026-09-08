-- Run as the database/bootstrap owner after application migrations. A cluster
-- role administrator must provision rag_reader first and grant it to the
-- bootstrap owner WITH ADMIN OPTION. This script performs database grants only.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rag_reader') THEN
        RAISE EXCEPTION 'rag_reader must be provisioned by the cluster role administrator';
    ELSIF EXISTS (
        SELECT 1 FROM pg_roles
        WHERE rolname = 'rag_reader'
          AND (
              rolcanlogin OR rolsuper OR rolcreatedb OR rolcreaterole
              OR rolreplication OR rolbypassrls
          )
    ) THEN
        RAISE EXCEPTION 'rag_reader has forbidden elevated attributes';
    END IF;
END
$$;

DO $$
BEGIN
    EXECUTE format(
        'REVOKE ALL PRIVILEGES ON DATABASE %I FROM rag_reader',
        current_database()
    );
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO rag_reader', current_database());
END
$$;

REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM rag_reader;
REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM rag_reader;
REVOKE CREATE ON SCHEMA public FROM rag_reader;
GRANT USAGE ON SCHEMA public TO rag_reader;
GRANT SELECT ON TABLE public.documents, public.chunks TO rag_reader;
