# Temporary legacy RAG contract

This document records the existing HTTP contract between `apps/rag-ui` and two legacy backend
routes. The routes are anonymous, temporary exceptions retained for that application only:

- `POST /rag-chat`
- `GET /audit-logs`

This freeze makes accidental drift visible while the RAG UI exists. It is not a long-term
compatibility promise, and no new consumer should integrate with either route. New anonymous
Assistant integrations must use the supported
`POST /public/assistants/{assistant_slug}/chat` endpoint.

## `POST /rag-chat`

The RAG UI sends an `application/json` object with these fields:

| Field | Type | Requirement |
| --- | --- | --- |
| `message` | string | Required. Empty strings are currently accepted. |
| `user_role` | string | Optional; defaults to `"user"`. Empty strings are currently accepted. |

Unknown object fields are ignored. `null` and non-string values for either declared field are
rejected with FastAPI's `422` validation response. A missing `message` and malformed JSON also
return `422`. These are characterized legacy behaviors, not recommendations for new APIs.

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

Existing orchestration exceptions return `500` with `{"detail": "<message>"}`. This records the
current behavior; it does not authorize exposing secrets, provider payloads, prompts, document
contents, or other sensitive details.

The route accepts anonymous requests and is limited to 20 requests per minute per SlowAPI client
key. Exceeding the limit returns `429` with the existing structured rate-limit error. Maintenance
mode blocks the route with `503` and the generic `maintenance_mode` response. When maintenance is
disabled, requests proceed normally.

## `GET /audit-logs`

The RAG UI sends an anonymous `GET` request without a query parameter. The optional integer
`limit` parameter defaults to the configured `AUDIT_LOG_LIMIT`, currently `10`, and the effective
value is forwarded directly to persistence. Explicit positive, zero, negative, and arbitrarily
large integers are currently accepted without clamping. If repeated, the last `limit` value wins.
A non-integer value returns FastAPI's `422` validation response.

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
      "keyword_match": true
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
      "keyword_match": false
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

The route accepts anonymous requests and is limited to 60 requests per minute per SlowAPI client
key. Unlike `/rag-chat`, `/audit-logs` is not classified as public Assistant traffic by the
maintenance middleware and remains reachable during maintenance mode.

## Change and retirement rule

The RAG UI and these backend routes form one temporary consumer-specific boundary. Any retirement,
migration, authentication change, validation change, or response redesign must update
`apps/rag-ui` and the backend routes together in a separately scoped change. Do not introduce an
administrator alias or direct another consumer to these routes as a migration shortcut.
