# Temporary legacy RAG contract

This document records the protected internal/debug contract between `apps/rag-ui` and two legacy
backend routes retained for that application only:

- `POST /rag-chat`
- `GET /audit-logs`

Both routes require the existing opaque HTTP-only administrator session cookie and the
`administrator` role. The browser first restores that session through `GET /admin/auth/me` and
sends credentials with subsequent requests. No administrator token or API key is exposed to
frontend JavaScript, browser storage, build-time configuration, or query strings.

This contract is not a long-term compatibility promise, and no new consumer should integrate with
either route. New anonymous Assistant integrations must use the supported
`POST /public/assistants/{assistant_slug}/chat` endpoint.

## `POST /rag-chat`

The RAG UI sends an `application/json` object with these fields:

| Field | Type | Requirement |
| --- | --- | --- |
| `message` | string | Required; at most 4,000 characters. Empty strings remain accepted. |
| `user_role` | string or null | Optional role narrowing hint; never an authorization claim. |

Unknown object fields are ignored but still count toward the raw request-body limit. A null or
omitted `user_role` selects the first server-permitted role; an empty string has the same behavior.
Non-string role values, a missing or non-string `message`, and malformed JSON return `422`.
Messages longer than 4,000 characters return `422` without invoking RAG orchestration. The raw
encoded request body is independently limited to 32,768 bytes and larger bodies return `413`
before body parsing or orchestration.

The server derives permitted retrieval roles from the authenticated administrator role. The
current sole administrator role is explicitly mapped to the five established demo roles:
`doctor`, `nurse`, `analyst`, `manager`, and `agent`. A supplied `user_role` can select one role
from that set but cannot add a role; unknown or unpermitted roles return the standard administrator
`403` response. Retrieval, audit lookup, and cache keys receive only this validated effective role,
so a cached response from one role cannot cross into another role's authorization context.

The success response is an object containing `reply`, `sources`, and `evaluation`. Source ID and
source array order are preserved:

```json
{
  "reply": {
    "answer": "Review the checklist and document consent.",
    "source_ids": ["chunk-20", "chunk-10"]
  },
  "sources": [
    {"id": "chunk-20", "text": "The checklist must be reviewed."},
    {"id": "chunk-10", "text": "Consent must be documented."}
  ],
  "evaluation": {
    "sentences": [],
    "metrics": {
      "groundedness_score": 1.0,
      "verified_sentences": 1,
      "unsupported_claims": 0,
      "total_sentences": 1,
      "citation_count": 2
    }
  }
}
```

The RAG UI reads `reply.answer`, `reply.source_ids`, every source's `id` and `text`, and the
`groundedness_score`, `verified_sentences`, `total_sentences`, and `citation_count` evaluation
metrics. The other evaluation values shown above remain preserved legacy output.

No retrieved context is a successful `200` response, not an error:

```json
{
  "reply": {
    "answer": "I could not find relevant information in the provided documents.",
    "source_ids": []
  },
  "sources": [],
  "evaluation": {
    "sentences": [],
    "metrics": {
      "groundedness_score": 0,
      "verified_sentences": 0,
      "unsupported_claims": 0,
      "total_sentences": 0,
      "citation_count": 0
    }
  }
}
```

Unexpected orchestration failures return the stable `500` body
`{"detail": "Internal server error"}`. Raw provider, database, prompt, document, credential, and
exception details are never returned.

Anonymous and invalid sessions receive the established administrator `401` response before RAG
work. The route remains limited to 20 requests per minute per SlowAPI client key. Maintenance mode
blocks it with the generic `503 maintenance_mode` response. Successful and internal-error responses
include `Cache-Control: no-store` because answers and sources are debug-sensitive.

## `GET /audit-logs`

The RAG UI sends an authenticated `GET` request without a query parameter. The optional integer
`limit` defaults to `AUDIT_LOG_LIMIT` (`10`) and accepts values from 1 through 200 inclusive. Zero,
negative, malformed, larger-than-maximum, and excessively large values return `422` before
persistence. Repeated values retain FastAPI's last-value behavior when that final value is valid.
Persistence therefore never receives an unbounded caller-controlled limit.

A successful request returns a top-level JSON array. An empty result is `[]` with status `200`.
Rows are selected by `id` descending, so the newest row is first, and the SQL query applies the
effective limit. A representative item is:

```json
{
  "id": 12,
  "timestamp": "2026-08-31T12:01:00+00:00",
  "user_role": "manager",
  "question": "What is required?",
  "reply": {
    "answer": "Use the checklist.",
    "source_ids": ["chunk-2", "chunk-1"]
  },
  "metrics": {
    "retrieval_time": 12.5,
    "llm_time": 25.0,
    "total_time": 37.5,
    "cache_hit": false,
    "input_tokens": 4,
    "output_tokens": 9
  },
  "queries": ["What is required?", "Which checklist applies?"],
  "retrieved_chunks": [
    {
      "rank": 1,
      "id": "chunk-2",
      "doc_id": "document-2",
      "distance": 0.1,
      "hybrid_score": 0.9,
      "text_snippet": "Review the checklist.",
      "keyword_match": 0.375
    }
  ],
  "reranked_chunks": [
    {
      "rank": 1,
      "id": "chunk-1",
      "doc_id": "document-1",
      "distance": 0.2,
      "hybrid_score": 0.8,
      "text_snippet": "Document consent.",
      "keyword_match": 0.0
    }
  ],
  "evaluation": {
    "sentences": [],
    "metrics": {
      "groundedness_score": 1.0,
      "verified_sentences": 1,
      "unsupported_claims": 0,
      "total_sentences": 1,
      "citation_count": 2
    }
  }
}
```

The RAG UI expects the listed top-level debug fields but does not read `evaluation`; `evaluation` is
nevertheless preserved legacy output and must not be removed or reshaped as part of this freeze. It
renders every metric shown above and every retrieved/reranked chunk field shown above.
`keyword_match` is a JSON number produced from PostgreSQL's text-search rank, not a boolean. Both
retrieved and reranked items must preserve that numeric type because the RAG UI invokes
`keyword_match.toFixed(3)`.

The route requires an authenticated administrator and is limited to 60 requests per minute per
SlowAPI client key. Unlike `/rag-chat`, `/audit-logs` is not classified as public Assistant traffic
by the maintenance middleware and remains reachable during maintenance mode. Successful responses
include `Cache-Control: no-store`. Unexpected persistence failures use the same stable, generic
`500` response as RAG chat and never expose raw exception text.

## Change and retirement rule

The RAG UI and these backend routes form one temporary consumer-specific boundary. Any retirement
or response redesign must update `apps/rag-ui` and the backend routes together. Do not introduce an
administrator alias or direct another consumer to these routes as a migration shortcut.
