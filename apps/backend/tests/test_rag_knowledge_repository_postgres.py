import os
from contextlib import contextmanager
from dataclasses import dataclass
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.types.json import Jsonb

import infrastructure.database.connection as database_connection
from assistant.infrastructure.repositories.rag_knowledge import PostgresRagKnowledgeRepository
from core.config import DATABASE_URL, EMBEDDING_VECTOR_DIMENSIONS


@dataclass(frozen=True)
class MigratedRagDatabase:
    schema: str
    connection_factory: object


def _require_database() -> None:
    required = os.getenv("RAG_REPOSITORY_POSTGRES_REQUIRED") == "true" or os.getenv("CI") == "true"
    if not DATABASE_URL:
        if required:
            pytest.fail("DATABASE_URL is required for RAG repository PostgreSQL tests")
        pytest.skip("DATABASE_URL is not configured")
    try:
        with psycopg.connect(DATABASE_URL, connect_timeout=2) as connection:
            connection.execute("SELECT 1")
    except psycopg.OperationalError as exc:
        if required:
            pytest.fail(f"Required PostgreSQL test database is unavailable: {exc}")
        pytest.skip(f"PostgreSQL test database is unavailable: {exc}")


@pytest.fixture(scope="module")
def migrated_rag_database():
    _require_database()
    schema = f"rag_contract_{uuid4().hex}"
    original_get_connection = database_connection.get_connection

    def connection_factory():
        connection = original_get_connection()
        connection.execute(sql.SQL("SET search_path TO {}, public").format(sql.Identifier(schema)))
        return connection

    with original_get_connection() as connection:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))

    database_connection.get_connection = connection_factory
    try:
        database_connection.init_db()
    finally:
        database_connection.get_connection = original_get_connection

    try:
        yield MigratedRagDatabase(schema, connection_factory)
    finally:
        with original_get_connection() as connection:
            connection.execute(
                sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema))
            )


def _embedding(first: float = 1.0, second: float = 0.0) -> list[float]:
    return [first, second] + [0.0] * (EMBEDDING_VECTOR_DIMENSIONS - 2)


def _insert_assistant(connection, assistant_id: UUID) -> None:
    connection.execute(
        """INSERT INTO assistants (id, slug, name, status, visibility)
           VALUES (%s, %s, %s, 'active', 'private') ON CONFLICT (id) DO NOTHING""",
        (str(assistant_id), f"assistant-{assistant_id.hex}", f"Assistant {assistant_id.hex}"),
    )


def _insert_document(
    connection,
    *,
    document_id: str,
    assistant_id: UUID,
    retrieval_state: str = "enabled",
) -> None:
    _insert_assistant(connection, assistant_id)
    connection.execute(
        """INSERT INTO documents
           (id, doc_type, access_roles, assistant_id, retrieval_state)
           VALUES (%s, 'text', '[]'::jsonb, %s, %s)""",
        (document_id, str(assistant_id), retrieval_state),
    )


def _insert_chunk(
    connection,
    *,
    chunk_id: str,
    document_id: str,
    assistant_id: UUID,
    text: str,
    roles: tuple[str, ...],
    embedding: list[float] | None = None,
) -> None:
    connection.execute(
        """INSERT INTO chunks (id, doc_id, text, embedding, access_roles, assistant_id)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        (
            chunk_id,
            document_id,
            text,
            embedding or _embedding(),
            Jsonb(list(roles)),
            str(assistant_id),
        ),
    )


def _search(database, assistant_id, query, role, *, limit=8):
    return PostgresRagKnowledgeRepository(database.connection_factory).search(
        assistant_id=assistant_id,
        query_embedding=_embedding(),
        query=query,
        access_role=role,
        limit=limit,
    )


def test_migrated_schema_satisfies_the_independent_rag_contract(migrated_rag_database):
    assistant_id = uuid4()
    document_id = f"schema-document-{uuid4()}"
    chunk_id = f"schema-chunk-{uuid4()}"
    with migrated_rag_database.connection_factory() as connection:
        _insert_document(connection, document_id=document_id, assistant_id=assistant_id)
        _insert_chunk(
            connection,
            chunk_id=chunk_id,
            document_id=document_id,
            assistant_id=assistant_id,
            text="Surgical checklist contract",
            roles=("doctor",),
        )

    matches = _search(migrated_rag_database, assistant_id, "surgical checklist", "doctor")

    assert len(matches) == 1
    assert matches[0]["id"] == chunk_id
    assert matches[0]["doc_id"] == document_id
    assert matches[0]["text"] == "Surgical checklist contract"
    assert matches[0]["access_roles"] == ["doctor"]
    assert matches[0]["distance"] == pytest.approx(0.0)
    assert matches[0]["keyword_match"] > 0
    assert matches[0]["hybrid_score"] == pytest.approx(
        (1 - matches[0]["distance"]) * 0.8 + matches[0]["keyword_match"] * 0.2
    )

    with migrated_rag_database.connection_factory() as connection:
        text_search = connection.execute(
            "SELECT text_search FROM chunks WHERE id = %s", (chunk_id,)
        ).fetchone()[0]
        indexes = {
            row[0]
            for row in connection.execute(
                "SELECT indexname FROM pg_indexes WHERE schemaname = %s",
                (migrated_rag_database.schema,),
            ).fetchall()
        }
    assert text_search is not None
    assert {
        "chunks_embedding_hnsw_idx",
        "chunks_text_search_idx",
        "chunks_assistant_id_idx",
        "documents_assistant_id_idx",
        "documents_assistant_retrieval_state_idx",
    } <= indexes


def test_repository_enforces_assistant_isolation_on_chunks_and_documents(migrated_rag_database):
    assistant_a = uuid4()
    assistant_b = uuid4()
    document_a = f"assistant-a-{uuid4()}"
    document_b = f"assistant-b-{uuid4()}"
    with migrated_rag_database.connection_factory() as connection:
        _insert_document(connection, document_id=document_a, assistant_id=assistant_a)
        _insert_document(connection, document_id=document_b, assistant_id=assistant_b)
        _insert_chunk(
            connection,
            chunk_id=f"chunk-a-{uuid4()}",
            document_id=document_a,
            assistant_id=assistant_a,
            text="Highly relevant shared policy",
            roles=("doctor",),
        )
        _insert_chunk(
            connection,
            chunk_id=f"chunk-b-{uuid4()}",
            document_id=document_b,
            assistant_id=assistant_b,
            text="Highly relevant shared policy",
            roles=("doctor",),
        )

    assert {
        row["doc_id"]
        for row in _search(
            migrated_rag_database, assistant_a, "highly relevant shared policy", "doctor"
        )
    } == {document_a}
    assert {
        row["doc_id"]
        for row in _search(
            migrated_rag_database, assistant_b, "highly relevant shared policy", "doctor"
        )
    } == {document_b}


def test_repository_rejects_inconsistent_chunk_and_document_ownership(migrated_rag_database):
    assistant_a = uuid4()
    assistant_b = uuid4()
    document_a = f"mismatch-document-{uuid4()}"
    connection = migrated_rag_database.connection_factory()
    try:
        connection.execute("ALTER TABLE chunks DROP CONSTRAINT chunks_document_assistant_fkey")
        _insert_document(connection, document_id=document_a, assistant_id=assistant_a)
        _insert_assistant(connection, assistant_b)
        _insert_chunk(
            connection,
            chunk_id=f"mismatch-chunk-{uuid4()}",
            document_id=document_a,
            assistant_id=assistant_b,
            text="Cross Assistant secret",
            roles=("doctor",),
        )

        @contextmanager
        def same_connection_factory():
            yield connection

        repository = PostgresRagKnowledgeRepository(same_connection_factory)
        for requested_assistant in (assistant_a, assistant_b):
            assert (
                repository.search(
                    assistant_id=requested_assistant,
                    query_embedding=_embedding(),
                    query="Cross Assistant secret",
                    access_role="doctor",
                    limit=8,
                )
                == []
            )
    finally:
        connection.rollback()
        connection.close()


def test_repository_enforces_role_and_retrieval_state_isolation(migrated_rag_database):
    assistant_id = uuid4()
    enabled_document = f"enabled-{uuid4()}"
    disabled_document = f"disabled-{uuid4()}"
    ids = {
        "doctor": f"doctor-{uuid4()}",
        "manager": f"manager-{uuid4()}",
        "shared": f"shared-{uuid4()}",
        "disabled": f"disabled-{uuid4()}",
    }
    with migrated_rag_database.connection_factory() as connection:
        _insert_document(connection, document_id=enabled_document, assistant_id=assistant_id)
        _insert_document(
            connection,
            document_id=disabled_document,
            assistant_id=assistant_id,
            retrieval_state="disabled",
        )
        _insert_chunk(
            connection,
            chunk_id=ids["doctor"],
            document_id=enabled_document,
            assistant_id=assistant_id,
            text="exclusive keyword keyword keyword",
            roles=("doctor",),
        )
        _insert_chunk(
            connection,
            chunk_id=ids["manager"],
            document_id=enabled_document,
            assistant_id=assistant_id,
            text="exclusive keyword keyword keyword",
            roles=("manager",),
        )
        _insert_chunk(
            connection,
            chunk_id=ids["shared"],
            document_id=enabled_document,
            assistant_id=assistant_id,
            text="shared procedure",
            roles=("doctor", "manager"),
        )
        _insert_chunk(
            connection,
            chunk_id=ids["disabled"],
            document_id=disabled_document,
            assistant_id=assistant_id,
            text="exclusive keyword keyword keyword",
            roles=("doctor", "manager"),
        )

    doctor_ids = {
        row["id"]
        for row in _search(migrated_rag_database, assistant_id, "exclusive keyword", "doctor")
    }
    manager_ids = {
        row["id"]
        for row in _search(migrated_rag_database, assistant_id, "exclusive keyword", "manager")
    }
    analyst_ids = {
        row["id"]
        for row in _search(migrated_rag_database, assistant_id, "exclusive keyword", "analyst")
    }
    assert doctor_ids == {ids["doctor"], ids["shared"]}
    assert manager_ids == {ids["manager"], ids["shared"]}
    assert analyst_ids == set()
    assert ids["disabled"] not in doctor_ids | manager_ids


def test_repository_preserves_hybrid_ordering_weighting_and_result_limit(migrated_rag_database):
    assistant_id = uuid4()
    document_id = f"ranking-document-{uuid4()}"
    keyword_chunk = f"keyword-{uuid4()}"
    plain_chunk = f"plain-{uuid4()}"
    with migrated_rag_database.connection_factory() as connection:
        _insert_document(connection, document_id=document_id, assistant_id=assistant_id)
        _insert_chunk(
            connection,
            chunk_id=plain_chunk,
            document_id=document_id,
            assistant_id=assistant_id,
            text="unrelated content",
            roles=("doctor",),
        )
        _insert_chunk(
            connection,
            chunk_id=keyword_chunk,
            document_id=document_id,
            assistant_id=assistant_id,
            text="checklist checklist checklist",
            roles=("doctor",),
        )

    all_matches = _search(migrated_rag_database, assistant_id, "checklist", "doctor")
    limited = _search(migrated_rag_database, assistant_id, "checklist", "doctor", limit=1)

    assert [row["id"] for row in all_matches] == [keyword_chunk, plain_chunk]
    assert [row["hybrid_score"] for row in all_matches] == sorted(
        [row["hybrid_score"] for row in all_matches], reverse=True
    )
    assert limited == [all_matches[0]]


def test_repository_preserves_vector_candidate_bound(migrated_rag_database):
    assistant_id = uuid4()
    document_id = f"candidate-document-{uuid4()}"
    excluded_chunk = f"candidate-50-{uuid4()}"
    with migrated_rag_database.connection_factory() as connection:
        _insert_document(connection, document_id=document_id, assistant_id=assistant_id)
        for index in range(51):
            _insert_chunk(
                connection,
                chunk_id=excluded_chunk if index == 50 else f"candidate-{index}-{uuid4()}",
                document_id=document_id,
                assistant_id=assistant_id,
                text="needle needle needle" if index == 50 else "ordinary content",
                roles=("doctor",),
                embedding=_embedding(1.0, index / 100),
            )

    matches = _search(
        migrated_rag_database,
        assistant_id,
        "needle",
        "doctor",
        limit=51,
    )

    assert len(matches) == 50
    assert excluded_chunk not in {row["id"] for row in matches}


def test_rag_login_inherits_read_group_privileges_without_set_role(migrated_rag_database):
    suffix = uuid4().hex
    group_role_name = f"rag_reader_group_test_{suffix}"
    login_role_name = f"rag_reader_login_test_{suffix}"
    group_role_created = False
    login_role_created = False
    assistant_id = uuid4()
    document_id = f"privilege-document-{uuid4()}"
    chunk_id = f"privilege-chunk-{uuid4()}"
    with migrated_rag_database.connection_factory() as connection:
        _insert_document(connection, document_id=document_id, assistant_id=assistant_id)
        _insert_chunk(
            connection,
            chunk_id=chunk_id,
            document_id=document_id,
            assistant_id=assistant_id,
            text="least privilege retrieval",
            roles=("doctor",),
        )

    try:
        with database_connection.get_connection() as connection:
            try:
                connection.execute(
                    sql.SQL(
                        "CREATE ROLE {} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
                        "INHERIT NOREPLICATION NOBYPASSRLS"
                    ).format(sql.Identifier(group_role_name))
                )
                group_role_created = True
                connection.execute(
                    sql.SQL(
                        "CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
                        "INHERIT NOREPLICATION NOBYPASSRLS"
                    ).format(sql.Identifier(login_role_name))
                )
                login_role_created = True
            except psycopg.errors.InsufficientPrivilege as exc:
                group_role_created = False
                login_role_created = False
                pytest.skip(f"PostgreSQL test user cannot create the RAG role topology: {exc}")
            connection.execute(
                sql.SQL("GRANT {} TO {}").format(
                    sql.Identifier(group_role_name), sql.Identifier(login_role_name)
                )
            )
            database_name = connection.execute("SELECT current_database()").fetchone()[0]
            connection.execute(
                sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                    sql.Identifier(database_name), sql.Identifier(group_role_name)
                )
            )
            connection.execute(
                sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(
                    sql.Identifier(migrated_rag_database.schema),
                    sql.Identifier(group_role_name),
                )
            )
            connection.execute(
                sql.SQL("GRANT SELECT ON {}.documents, {}.chunks TO {}").format(
                    sql.Identifier(migrated_rag_database.schema),
                    sql.Identifier(migrated_rag_database.schema),
                    sql.Identifier(group_role_name),
                )
            )

        def login_connection_factory():
            connection = database_connection.get_connection()
            try:
                connection.execute(
                    sql.SQL("SET SESSION AUTHORIZATION {}").format(sql.Identifier(login_role_name))
                )
            except psycopg.errors.InsufficientPrivilege as exc:
                connection.close()
                pytest.skip(f"PostgreSQL test user cannot emulate login authentication: {exc}")
            connection.execute(
                sql.SQL("SET search_path TO {}, public").format(
                    sql.Identifier(migrated_rag_database.schema)
                )
            )
            return connection

        with login_connection_factory() as connection:
            assert connection.execute("SELECT session_user, current_user").fetchone() == (
                login_role_name,
                login_role_name,
            )
            assert connection.execute("SELECT count(*) FROM documents").fetchone()[0] >= 1
            assert connection.execute("SELECT count(*) FROM chunks").fetchone()[0] >= 1

        matches = PostgresRagKnowledgeRepository(login_connection_factory).search(
            assistant_id=assistant_id,
            query_embedding=_embedding(),
            query="least privilege retrieval",
            access_role="doctor",
            limit=8,
        )
        assert [row["id"] for row in matches] == [chunk_id]

        denied_statements = (
            "INSERT INTO documents (id, doc_type, assistant_id, retrieval_state) VALUES ('denied-document', 'text', 'denied', 'enabled')",
            f"UPDATE documents SET status = 'indexed' WHERE id = '{document_id}'",
            f"DELETE FROM documents WHERE id = '{document_id}'",
            "TRUNCATE documents CASCADE",
            f"INSERT INTO chunks (id, doc_id, text, embedding, access_roles, assistant_id) SELECT 'denied-chunk', doc_id, text, embedding, access_roles, assistant_id FROM chunks WHERE id = '{chunk_id}'",
            f"UPDATE chunks SET text = 'denied' WHERE id = '{chunk_id}'",
            f"DELETE FROM chunks WHERE id = '{chunk_id}'",
            "TRUNCATE chunks",
            "INSERT INTO ingestion_jobs (id, source_url, status, created_at) VALUES ('denied-job', 'https://example.test', 'pending', NOW())",
            f"INSERT INTO document_ingestion_jobs (id, document_id, stage, status, progress) VALUES ('denied-document-job', '{document_id}', 'queued', 'queued', 0)",
            "INSERT INTO audit_logs (user_role, question) VALUES ('doctor', 'denied')",
            "INSERT INTO assistants (id, slug, name, status, visibility) VALUES ('denied-assistant', 'denied-assistant', 'Denied', 'inactive', 'private')",
            f"CREATE TABLE {migrated_rag_database.schema}.denied_object (id integer)",
        )
        for statement in denied_statements:
            with login_connection_factory() as connection:
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    connection.execute(statement)
    finally:
        if group_role_created or login_role_created:
            with database_connection.get_connection() as connection:
                if group_role_created and login_role_created:
                    connection.execute(
                        sql.SQL("REVOKE {} FROM {}").format(
                            sql.Identifier(group_role_name), sql.Identifier(login_role_name)
                        )
                    )
                if login_role_created:
                    connection.execute(
                        sql.SQL("DROP OWNED BY {}").format(sql.Identifier(login_role_name))
                    )
                    connection.execute(
                        sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(login_role_name))
                    )
                if group_role_created:
                    connection.execute(
                        sql.SQL("DROP OWNED BY {}").format(sql.Identifier(group_role_name))
                    )
                connection.execute(
                    sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(group_role_name))
                )
