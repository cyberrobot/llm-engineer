-- Run once as the database/bootstrap owner. For a non-superuser bootstrap owner,
-- a cluster role administrator must first create rag_migrator with the attributes
-- below and grant it to the bootstrap owner WITH ADMIN OPTION. A superuser can use
-- this script to create it directly. Deployment creates a separate LOGIN role,
-- grants it membership in rag_migrator, and supplies that login only through
-- RAG_MIGRATION_DATABASE_URL.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rag_migrator') THEN
        CREATE ROLE rag_migrator
            NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE INHERIT
            NOREPLICATION NOBYPASSRLS;
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
    IF NOT EXISTS (
        SELECT 1
        FROM pg_auth_members membership
        JOIN pg_roles granted_role ON granted_role.oid = membership.roleid
        JOIN pg_roles member_role ON member_role.oid = membership.member
        WHERE granted_role.rolname = 'rag_migrator'
          AND member_role.rolname = current_user
          AND membership.admin_option
    ) THEN
        EXECUTE format('GRANT rag_migrator TO %I WITH ADMIN OPTION', current_user);
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
