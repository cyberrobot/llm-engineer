# RAG persistence contract

The legacy `/rag-chat` path remains in `apps/backend`, but its application retrieval code depends
on the read-only `RagKnowledgeRepository` port. `PostgresRagKnowledgeRepository` owns the hybrid
PostgreSQL query. Ingestion continues to use its existing write repositories and credentials.

## Required schema

RAG reads `documents.id`, `documents.assistant_id`, and `documents.retrieval_state`, plus
`chunks.id`, `chunks.doc_id`, `chunks.assistant_id`, `chunks.access_roles`, `chunks.embedding`,
`chunks.text`, and `chunks.text_search`. The `chunks.doc_id` relationship must resolve to a document.
The current migration path provides a 1536-dimensional pgvector column, an English full-text trigger
for `text_search`, HNSW and GIN retrieval indexes, chunk Assistant indexes, and document Assistant
and retrieval-state indexes.

The SQL query itself requires both chunk and document ownership to match the requested Assistant,
requires `documents.retrieval_state = 'enabled'`, and applies the requested role through JSONB's `?`
operator before ranking. It bounds vector candidates at 50, calculates cosine distance with `<=>`,
uses `plainto_tsquery('english', ...)` and `ts_rank`, applies the configured vector and keyword
weights, orders by hybrid score, and applies the requested result limit. Application orchestration
retains the existing maximum-distance cutoff.

## Least-privilege role

After migrations, a database owner can apply
`infrastructure/database/rag_read_role.sql` with `psql`. It creates or hardens the `rag_reader`
group role without login credentials, removes table and sequence privileges in `public`, denies
schema creation, and grants only database `CONNECT`, schema `USAGE`, and `SELECT` on `documents`
and `chunks`. Do not grant this role membership in administrative or write-capable roles. Audit
effective privileges as well as direct grants if a deployment changes PostgreSQL's `PUBLIC` grants.

Create deployment-specific login credentials outside source control and grant that login membership
in `rag_reader`. The backend currently has one `DATABASE_URL` and does **not** activate a distinct
RAG credential; configuring it with `rag_reader` would also remove the writes needed by ingestion,
audit, and administration. Activating separate credentials later requires wiring a distinct RAG
connection factory while leaving ingestion on its write credential.

## Verification

Run the real migrated-schema, isolation, ranking, and privilege checks against disposable
PostgreSQL state:

```sh
cd apps/backend
RAG_REPOSITORY_POSTGRES_REQUIRED=true pytest -q tests/test_rag_knowledge_repository_postgres.py
```

The test exercises the real repository after direct fixture inserts, checks the generated
`text_search` value and required indexes, proves Assistant/role/retrieval-state isolation, and—when
the configured test user can create roles—executes retrieval under a read role and verifies that
document, chunk, ingestion-job, and administrative writes are denied. If the test database user
cannot create roles, that test skips with the PostgreSQL permission error; deployment validation
must then apply the SQL as the database owner and repeat the grant audit.
