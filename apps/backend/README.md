# Backend

FastAPI backend for the AI Discovery Assistant.

## Run locally

Install dependencies from `requirements.txt`, copy `.env.example` to `.env`, and run:

```sh
python -m uvicorn main:app --reload
```

The canonical application entry point is `main:app`.

## AI configuration

Assistant chat uses the provider selected entirely through environment variables:

- `AI_PROVIDER`: provider identifier; currently `openai` (default)
- `OPENAI_API_KEY`: required when Assistant chat is called
- `OPENAI_MODEL`: model identifier (default: `gpt-5.5`)
- `AI_REQUEST_TIMEOUT`: request timeout in seconds (default: `30`)

Assistant chat retrieves relevant knowledge before generation. With `DATABASE_URL` configured,
retrieval uses the existing pgvector `chunks` and `documents` tables. Without a database it uses
the small manually curated seed fixture in `assistant/infrastructure/seed_knowledge.py`.

The OpenAI client is created lazily, so health endpoints and non-AI workflows can start
without provider credentials. Missing or invalid AI configuration is returned as a service
availability error when chat is requested.

## Website content processing

Raw `WebsiteDocument` values from the website loader are transformed entirely in memory:

```text
WebsiteDocument -> HTML extraction -> text normalisation -> semantic chunking
                -> ContentProcessingResult
```

The extractor prefers `main`, `article`, `role="main"`, recognised content containers, and then
the document body. Scripts, styles, embedded content, hidden elements, navigation, footers, and
conservatively recognised overlays or cookie controls are excluded. Its canonical representation
is Markdown-like plain text: headings use `#` markers, paragraphs use blank-line boundaries, list
items keep ordered or unordered markers, block quotes use `>`, and simple table cells are separated
with ` | `. This representation is deterministic and contains no HTML-parser objects.

The cleaner applies Unicode NFC normalisation, removes zero-width and control characters,
normalises whitespace, preserves semantic line boundaries, and removes only adjacent duplicate
lines. The SHA-256 document content hash is calculated from the final cleaned text.

Chunking is character-based; it does not report character counts as tokens. It prefers section and
paragraph boundaries, then uses the existing sentence segmenter, with word and hard character
splits only as fallbacks. Chunk order, hashes, UUIDs, and heading-path metadata are deterministic.
Overlap copies at most the configured number of characters from the prior base chunk, trims to a
word boundary when possible, never copies a full prior chunk, and never makes a chunk exceed the
configured size. The minimum chunk size is honoured where the available content can satisfy it;
a whole document shorter than that minimum remains one useful chunk rather than being discarded.

Configuration is environment-driven:

- `INGESTION_CHUNK_SIZE_CHARACTERS` (default `1200`)
- `INGESTION_CHUNK_OVERLAP_CHARACTERS` (default `150`)
- `INGESTION_MIN_CHUNK_SIZE_CHARACTERS` (default `100`)
- `INGESTION_MIN_DOCUMENT_LENGTH_CHARACTERS` (default `50`)

Pages with no extracted body, too little cleaned content, or a recoverable page-level processing
failure are skipped with a structured warning while other pages continue. If no page creates a
chunk, the service raises `NoProcessableContentError` carrying the aggregate result and warnings.

Current extraction is intentionally conservative and does not render JavaScript or learn
cross-page boilerplate. The processing layer itself makes no OpenAI, database, vector-store, or
retrieval calls.

## Knowledge persistence

`KnowledgePersistenceService` accepts a `ContentProcessingResult` and stores its website documents
and chunks in the existing `documents` and `chunks` tables queried by pgvector retrieval:

```text
ContentProcessingResult -> duplicate check -> batch embeddings
                        -> atomic document/chunk write -> existing retrieval
```

Website documents are identified by their normalized source URL and retain the deterministic
document and chunk hashes produced by content processing. A unique partial index on document source
URL prevents duplicate website records without affecting existing uploaded documents. Unique
document/sequence and document/chunk-hash indexes reinforce chunk idempotency. Source URL, title,
heading path, access roles, and the fixed 1536-dimensional vector are stored alongside the existing
retrieval fields.

An identical document hash is a no-op: no chunks are rewritten and no embeddings are requested.
Changed documents use a document-level replacement strategy. All replacement embeddings are
generated in configurable batches before the database write; the document metadata update, old
chunk deletion, and new chunk insertion then occur in one transaction. This deliberately favors a
small, reliable transaction boundary over chunk-level vector reuse. PostgreSQL advisory transaction
locks serialize writes for the same source URL, while database uniqueness constraints prevent
concurrent duplicate documents or chunks. Provider and database failures are mapped to application
errors, and failed writes roll back without partial knowledge.

Configuration:

- `OPENAI_EMBEDDING_MODEL` (default `text-embedding-3-small`)
- `EMBEDDING_BATCH_SIZE` (default `100`)

The vector dimension remains a single canonical backend value matching the existing pgvector
schema. Persistence logs counts and timing but never chunk text, vectors, provider responses, or
credentials.

Chunk 7D does not run website ingestion end to end. Chunk 7E will orchestrate website loading,
content processing, this persistence service, and ingestion-job lifecycle updates. Background work,
job status transitions, and website ingestion API changes remain intentionally deferred.

## Validate

```sh
python -m pytest
ruff check .
ruff format --check .
python -m mypy .
```
