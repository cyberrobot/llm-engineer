-- Run with psql as the database owner after application migrations.
-- This group role intentionally has no login or credentials. Deployments create a
-- separate LOGIN role, grant it rag_reader membership, and supply that credential
-- only when the application supports a distinct RAG connection factory.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rag_reader') THEN
        CREATE ROLE rag_reader
            NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT
            NOREPLICATION NOBYPASSRLS;
    ELSE
        ALTER ROLE rag_reader
            NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT
            NOREPLICATION NOBYPASSRLS;
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
