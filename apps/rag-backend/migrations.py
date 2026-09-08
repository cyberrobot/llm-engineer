"""Versioned migrations owned exclusively by the standalone RAG service."""

import argparse
import os
from collections.abc import Sequence

import psycopg

MIGRATIONS: Sequence[tuple[str, str]] = (
    (
        "20260907_001_create_rag_audit_logs",
        """
        CREATE TABLE rag.audit_logs (
            id BIGSERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            user_role TEXT NOT NULL,
            question TEXT NOT NULL,
            queries JSONB NOT NULL DEFAULT '[]'::jsonb,
            reply JSONB NOT NULL DEFAULT '{}'::jsonb,
            retrieved_chunks JSONB NOT NULL DEFAULT '[]'::jsonb,
            reranked_chunks JSONB NOT NULL DEFAULT '[]'::jsonb,
            evaluation JSONB NOT NULL DEFAULT '{}'::jsonb,
            metrics JSONB NOT NULL DEFAULT '{}'::jsonb
        );
        CREATE INDEX audit_logs_timestamp_idx
            ON rag.audit_logs(timestamp DESC, id DESC);
        """,
    ),
)


def upgrade(database_url: str) -> list[str]:
    """Apply pending RAG migrations in one transaction per invocation."""
    applied: list[str] = []
    with psycopg.connect(database_url) as connection:
        connection.execute("SET LOCAL ROLE rag_migrator")
        connection.execute(
            """CREATE TABLE IF NOT EXISTS rag.schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )"""
        )
        installed = {
            row[0]
            for row in connection.execute(
                "SELECT version FROM rag.schema_migrations"
            ).fetchall()
        }
        for version, statement in MIGRATIONS:
            if version in installed:
                continue
            connection.execute(statement)
            connection.execute(
                "INSERT INTO rag.schema_migrations (version) VALUES (%s)", (version,)
            )
            applied.append(version)
    return applied


def status(database_url: str) -> list[str]:
    """Return applied migration versions without changing database state."""
    with psycopg.connect(database_url) as connection:
        connection.execute("SET LOCAL ROLE rag_migrator")
        relation = connection.execute(
            "SELECT to_regclass('rag.schema_migrations')"
        ).fetchone()
        if relation is None or relation[0] is None:
            return []
        return [
            row[0]
            for row in connection.execute(
                "SELECT version FROM rag.schema_migrations ORDER BY version"
            ).fetchall()
        ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage standalone RAG migrations")
    parser.add_argument("command", choices=("upgrade", "status"))
    args = parser.parse_args()
    database_url = os.getenv("RAG_MIGRATION_DATABASE_URL")
    if not database_url:
        parser.error("RAG_MIGRATION_DATABASE_URL must be configured")
    versions = (
        upgrade(database_url) if args.command == "upgrade" else status(database_url)
    )
    print("\n".join(versions) if versions else "No migrations to report.")


if __name__ == "__main__":
    main()
