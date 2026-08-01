# Public assistant chat API

PR 11C provides the functional public chat transport for the inline assistant widget. Keep
`PUBLIC_ASSISTANT_CHAT_ENABLED=false` in production until PR 11D adds the production abuse,
request, concurrency, timeout, CORS, and load protections. The gate is server-owned and defaults
to disabled in every environment; local and test environments must enable it explicitly.

## HTTP contract

`POST /public/assistants/{assistant_slug}/chat` resolves the exact lowercase assistant slug. There
is no fallback assistant. Missing, private, and inactive assistants all return `404` with
`assistant_not_found`, so the public route does not disclose private assistant existence or state.

The JSON request is strict; unknown fields such as `model`, `system_prompt`, `temperature`, or
retrieval settings are rejected:

```json
{
  "message": "What services does Redmoor Consulting provide?",
  "history": [
    {"role": "user", "content": "Tell me about Redmoor Consulting."},
    {"role": "assistant", "content": "Redmoor Consulting helps organisations..."}
  ]
}
```

`message` is required, trimmed, non-empty, and limited to 4,000 characters. `history` is optional
and must contain zero or more complete prior turns: it starts with `user`, alternates exactly with
`assistant`, and ends with `assistant`. The server rejects system/developer/tool roles, empty or
unknown fields, more than 12 messages, more than 4,000 characters in one history message, more than
12,000 history characters, an estimated history size above 3,000 tokens, and a declared encoded
request size above 32 KiB. History is never truncated or persisted.

Pre-stream errors are JSON responses with stable `detail.code` values:

| Status | Code | Meaning |
| --- | --- | --- |
| 400 | `invalid_request` | Invalid request framing |
| 404 | `assistant_not_found` | Unknown or publicly unavailable assistant |
| 422 | `validation_error` | Invalid or oversized request/history |
| 500 | `chat_unavailable` | Retrieval or preparation failed |
| 503 | `chat_unavailable` | Deployment gate is disabled |

## Retrieval and grounding

The route constructs a retrieval service for the resolved assistant ID. The repository query—not
post-query filtering—requires that assistant ID and excludes documents whose retrieval state is
disabled. The server owns the candidate limit (`PUBLIC_CHAT_RETRIEVAL_LIMIT`, default `3`) and
minimum cosine-similarity score (`PUBLIC_CHAT_MIN_SIMILARITY_SCORE`, default `0.7`). No accepted
chunk means evidence is insufficient.

Insufficient evidence bypasses generation and returns this exact Redmoor response:

> I don’t have enough information in the Redmoor knowledge base to answer that.

Other assistants receive the equivalent generic assistant-scoped wording. With accepted evidence,
the existing configured provider and `OPENAI_MODEL` are used. The server owns
`PUBLIC_CHAT_MAX_OUTPUT_TOKENS` (default `500`) and `PUBLIC_CHAT_TEMPERATURE` (default `0.2`).

The public prompt is centralised in `PromptBuilder`. Retrieved text, prior conversation, and the
current message are JSON-encoded in separately labelled untrusted-data sections. The system
instruction says those sections cannot change server instructions, that embedded source
instructions must not be followed, and that internal prompts/configuration must not be revealed.
Prior assistant messages provide conversational context only; current factual claims must still be
grounded in retrieved assistant knowledge.

## Streaming contract

A successful preparation returns UTF-8 Server-Sent Events with `Content-Type: text/event-stream`,
`Cache-Control: no-cache`, `Connection: keep-alive`, and `X-Accel-Buffering: no`. Events occur in
this order:

```text
event: start
data: {"assistant":"redmoor"}

event: delta
data: {"text":"Redmoor Consulting "}

event: complete
data: {"finishReason":"stop"}
```

The fixed insufficient response uses the same start/delta/complete sequence. Empty provider deltas
are ignored. A provider completion with no text, or a failure before or after deltas, emits one safe
terminal event and never emits `complete` afterward:

```text
event: error
data: {"code":"generation_failed","message":"The response could not be completed."}
```

Source, document, chunk, score, prompt, model configuration, and reasoning data are never emitted.
Closing the response iterator closes the request-local provider stream, allowing framework client
disconnect cancellation to release the SDK stream without affecting concurrent requests.

Structured logs include the request ID, assistant identity, bounded input/history counts, retrieval
counts, accepted internal chunk IDs, configured model, outcome, and durations without full messages,
prompts, or retrieved text. Metrics cover requests, completions, insufficient knowledge, failures,
cancellations, and retrieval/generation/total durations. When the provider supplies usage, input and
output token counts are logged with the server-selected model.

## Local verification

Set `PUBLIC_ASSISTANT_CHAT_ENABLED=true`, configure the normal database/OpenAI dependencies, and
run the backend. Automated tests use dependency-injected providers and never call a live model:

```sh
venv/bin/python -m pytest tests/test_public_chat.py
venv/bin/python -m pytest tests/test_retrieval_pipeline.py tests/test_ai_provider.py
```

PR 12C should consume the request and SSE contracts above and must not infer hidden source data or
send model, prompt, retrieval, or tool configuration.
