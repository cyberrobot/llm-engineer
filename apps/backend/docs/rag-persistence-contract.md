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
`infrastructure/database/rag_read_role.sql` with `psql`. It creates or hardens `rag_reader` as an
inheritable, non-login group role, removes table and sequence privileges in `public`, denies schema
creation, and grants only database `CONNECT`, schema `USAGE`, and `SELECT` on `documents` and
`chunks`. Do not grant this group role membership in administrative or write-capable roles. Audit
effective privileges as well as direct grants if a deployment changes PostgreSQL's `PUBLIC` grants.

Deployments create a separate inheritable login role and credential outside source control, then
grant that login membership in `rag_reader`. The login automatically inherits the group's RAG read
privileges and executes retrieval directly; no `SET ROLE` step is required. Ingestion and
administrative connections must continue using write-capable credentials. The backend currently has
one `DATABASE_URL` and does **not** activate a distinct RAG credential in this change. Activating
separate credentials later requires wiring a distinct RAG connection factory while leaving
ingestion and administration on their write credential.

## Verification

Run the real migrated-schema, isolation, ranking, and privilege checks against disposable
PostgreSQL state:

```sh
cd apps/backend
RAG_REPOSITORY_POSTGRES_REQUIRED=true pytest -q tests/test_rag_knowledge_repository_postgres.py
```

The test exercises the real repository after direct fixture inserts, checks the generated
`text_search` value and required indexes, proves Assistant/role/retrieval-state isolation, and—when
the configured test user can create roles—creates a non-login read group and a separate login member,
emulates authentication as that login without switching to the group, and verifies inherited reads,
real retrieval, and denied document, chunk, ingestion-job, administrative, and schema writes. If the
test database user cannot create roles or emulate login authentication, that test skips with the
PostgreSQL permission error; deployment validation must then apply the SQL as the database owner and
repeat the topology and grant checks.
