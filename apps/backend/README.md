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
cross-page boilerplate. Embedding generation and chunk/document persistence are intentionally
deferred to Chunk 7D; this layer makes no OpenAI, database, vector-store, or retrieval calls.

## Validate

```sh
python -m pytest
ruff check .
ruff format --check .
python -m mypy .
```
