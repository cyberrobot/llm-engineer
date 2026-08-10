# PR 7C Follow-up — Content Processing Reliability and Compliance

## Repository state

Expected branch: `feature/7c-content-processing-reliability`

Base branch: `origin/main`

Worktree: repository root

Dependencies: existing Chunk 7B `WebsiteLoader` contract and Chunk 7C content-processing pipeline on `main`

### Read first

- `AGENTS.md`
- `docs/architecture/repository-map.md`
- `docs/architecture/dependency-rules.md`
- `apps/backend/AGENTS.md`
- `apps/backend/README.md`

### Primary change area

- `apps/backend/assistant/application/content_processing_service.py`
- `apps/backend/assistant/application/ports/`
- `apps/backend/assistant/infrastructure/ingestion/html_content_extractor.py`
- `apps/backend/assistant/infrastructure/ingestion/semantic_text_chunker.py`
- focused content-processing tests under `apps/backend/tests/`

### Canonical implementation examples

- `apps/backend/assistant/application/safe_url.py` for log-safe source origins
- `apps/backend/assistant/application/ports/website_loader.py` for the current loader contract
- `apps/backend/assistant/infrastructure/ingestion/normalising_text_cleaner.py` for ordinary no-content handling through `None`

### Relevant symbols

- `ContentProcessingService`
- `ContentProcessingError`
- `ContentExtractor`, `TextCleaner`, `TextChunker`
- `HtmlContentExtractor`
- `SemanticTextChunker`
- `WebsiteLoader.load`
- `WebsiteDocument`

### Expected change surface

- explicit recoverable stage exceptions and safe unexpected-failure mapping
- whole-sequence minimum chunk-size normalisation
- conservative boilerplate matching and explicit deterministic title precedence
- accurate integration-test fixture naming and backend documentation
- targeted unit and controlled integration tests

### Excluded areas

- crawling, HTTP and sitemap behaviour
- embeddings, vector storage, persistence, retrieval, or reranking
- ingestion-job execution, retries, workers, and API endpoints
- cross-page or LLM-based boilerplate detection
- token-based chunk configuration
- new loader result wrappers or dependencies

### Unknowns Codex must verify

- whether a real `WebsiteLoadResult` exists (none exists at task start)
- whether loader-provided titles are authoritative (the `WebsiteDocument.title` field is explicit loader metadata and remains first precedence)
- whether crawl-level metadata is represented elsewhere (processing currently consumes only `Sequence[WebsiteDocument]`)

---

## Objective

Correct the remaining reliability and specification-compliance defects in the existing Chunk 7C content-processing pipeline without redesigning or reimplementing it.

## Current architecture

`WebsiteLoader.load()` and `load_single_page()` return `list[WebsiteDocument]`. `ContentProcessingService.process()` accepts `Sequence[WebsiteDocument]` and orchestrates application-owned extractor, cleaner, and chunker ports. Beautiful Soup and semantic chunking implementations remain infrastructure adapters. Processing is deterministic and in-memory, and has no embedding, persistence, or network side effects.

## Required implementation

1. Define a small application-owned recoverable stage-error hierarchy. Catch only the matching recoverable exception at each stage as a page warning; wrap any other `Exception` in `ContentProcessingError`, preserve it as `__cause__`, emit only safe structured error metadata, and abort processing.
2. Preserve `None` and `[]` as ordinary no-content outcomes. Warnings and logs must not expose underlying exception messages, raw page content, URL paths/queries/fragments, or parser details.
3. Replace tail-only minimum-size correction with deterministic best-effort normalisation across every ordered base chunk. Prefer merge backward, merge forward, then boundary-aware redistribution. Retain meaningful unavoidable short chunks and keep every chunk at or below the configured maximum.
4. Retain the earliest chunk heading path when merging. Never fabricate metadata, reorder or duplicate text, or weaken deterministic hashes and IDs.
5. Replace broad `social` and `share` class/id matching with specific boilerplate signals while keeping clear cookie, overlay, navigation, footer, and hidden-content removal.
6. Make and test title precedence explicitly as loader title, Open Graph title, Twitter title, HTML title, first meaningful `h1`, then `None`; reject blank, excessive, and known boilerplate candidates.
7. Keep the real `Sequence[WebsiteDocument]` contract and rename misleading test helpers that imply `WebsiteLoadResult` exists.
8. Update backend documentation for error classification, whole-sequence minimum-size semantics, conservative boilerplate removal, loader contract, and title precedence.

## Acceptance criteria

- [ ] Recoverable extraction, cleaning, and chunking errors skip only the affected page with safe generic warnings.
- [ ] Unexpected failures at every stage abort with `ContentProcessingError` chained from the original exception and safe error-level logging.
- [ ] Valid pages and chunks retain input order; warnings do not reveal underlying error text.
- [ ] Avoidable short first, middle, and final chunks are merged or rebalanced across the whole sequence.
- [ ] Unavoidable short chunks retain all meaningful ordered text, terminate, and do not exceed the maximum.
- [ ] Repeated chunking produces identical text, sequence, hashes, IDs, and heading metadata.
- [ ] `social-proof` and `share-price` content survives, while recognised sharing controls, cookie controls, modal overlays, navigation, footer, and hidden content remain excluded.
- [ ] Title precedence and invalid-title fallback cases are explicit and deterministic.
- [ ] No `WebsiteLoadResult` abstraction is added; integration coverage uses real processing adapters over website documents without external side effects.
- [ ] Existing character-based configuration, hashes, IDs, overlap, warning aggregation, and `NoProcessableContentError` behaviour remain compatible.

## Tests to add or update

- `apps/backend/tests/test_content_processing_service.py`: recoverable and unexpected failures for all stages, chaining, safe warnings/logs, and ordering.
- `apps/backend/tests/test_semantic_text_chunker.py`: short first/middle/final chunks, unavoidable short chunk, maximum size, ordering, text retention, and determinism.
- `apps/backend/tests/test_html_content_extractor.py`: conservative class/id matching and complete title precedence/fallback coverage.
- `apps/backend/tests/test_content_processing_integration.py`: accurately named document fixture, multiple real documents, skipped low-value input, ordered deterministic output, and no external side effects.

## Verification commands

```bash
venv/bin/python -m pytest -q -o "addopts=" --strict-markers \
  apps/backend/tests/test_content_processing_service.py \
  apps/backend/tests/test_semantic_text_chunker.py \
  apps/backend/tests/test_html_content_extractor.py \
  apps/backend/tests/test_content_processing_integration.py
cd apps/backend
../../venv/bin/python -m pytest -q -o "addopts=" --strict-markers tests
../../venv/bin/python -m ruff check .
../../venv/bin/python -m ruff format --check .
../../venv/bin/python -m mypy assistant
../../venv/bin/python -c "import main"
```
