-- Run once as the database/bootstrap owner. A cluster role administrator must
-- provision rag_migrator first and grant it to the bootstrap owner WITH ADMIN
-- OPTION. This script performs database/schema grants only.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rag_migrator') THEN
        RAISE EXCEPTION 'rag_migrator must be provisioned by the cluster role administrator';
    ELSIF EXISTS (
        SELECT 1 FROM pg_roles
        WHERE rolname = 'rag_migrator'
          AND (
              rolcanlogin OR rolsuper OR rolcreatedb OR rolcreaterole
              OR rolreplication OR rolbypassrls
          )
    ) THEN
        RAISE EXCEPTION 'rag_migrator has forbidden elevated attributes';
    END IF;
END
$$;

DO $$
BEGIN
    EXECUTE format(
        'REVOKE ALL PRIVILEGES ON DATABASE %I FROM rag_migrator',
        current_database()
    );
    EXECUTE format(
        'GRANT CONNECT ON DATABASE %I TO rag_migrator',
        current_database()
    );
    IF NOT pg_has_role(current_user, 'rag_migrator', 'SET') THEN
        RAISE EXCEPTION 'bootstrap owner must be able to SET ROLE rag_migrator';
    END IF;
END
$$;

REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM rag_migrator;
REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM rag_migrator;
REVOKE CREATE ON SCHEMA public FROM rag_migrator;

CREATE SCHEMA IF NOT EXISTS rag AUTHORIZATION rag_migrator;
ALTER SCHEMA rag OWNER TO rag_migrator;
REVOKE ALL ON SCHEMA rag FROM PUBLIC;
GRANT USAGE, CREATE ON SCHEMA rag TO rag_migrator;
