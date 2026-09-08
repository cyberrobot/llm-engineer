-- Run once per PostgreSQL cluster as a cluster role administrator. These
-- NOLOGIN roles own or receive privileges but are never application credentials.
DO $$
DECLARE
    role_name text;
BEGIN
    FOREACH role_name IN ARRAY ARRAY['rag_reader', 'rag_migrator', 'rag_auth_audit']
    LOOP
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = role_name) THEN
            EXECUTE format(
                'CREATE ROLE %I NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE '
                'INHERIT NOREPLICATION NOBYPASSRLS',
                role_name
            );
        ELSIF EXISTS (
            SELECT 1 FROM pg_roles
            WHERE rolname = role_name
              AND (
                  rolcanlogin OR rolsuper OR rolcreatedb OR rolcreaterole
                  OR rolreplication OR rolbypassrls
              )
        ) THEN
            RAISE EXCEPTION '% has forbidden elevated attributes', role_name;
        END IF;
    END LOOP;
END
$$;
