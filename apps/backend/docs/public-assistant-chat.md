# Public assistant chat API

`POST /public/assistants/{assistant_slug}/chat` is an unauthenticated, deployment-gated SSE
endpoint. It remains disabled unless `PUBLIC_ASSISTANT_CHAT_ENABLED=true`. Production startup fails
closed when any required protection setting is absent, malformed, unlimited, internally
inconsistent, or dependent on disabled shared rate-limit storage.

## Request and browser contract

Requests require `Content-Type: application/json` (a charset parameter is accepted). Browser
requests must send an exact `Origin` listed in `PUBLIC_CHAT_ALLOWED_ORIGINS`; direct non-browser
clients without `Origin` are accepted and receive the same limits. Credentials are not used.
`X-Anonymous-Session-ID` is optional, unverified, and only supplementary: the Uvicorn-resolved
client address remains the authoritative limit key, so rotating IDs cannot bypass IP controls.

```json
{
  "message": "What services does Redmoor Consulting provide?",
  "history": [
    {"role": "user", "content": "Tell me about Redmoor Consulting."},
    {"role": "assistant", "content": "Redmoor Consulting helps organisations..."}
  ]
}
```

History contains complete `user`/`assistant` turns only. The boundary rejects unsupported fields,
roles, malformed JSON, unsupported media types, excessive message/history counts, per-message and
aggregate history sizes, and raw UTF-8 JSON bodies over the configured byte limit. Raw bodies are
bounded before FastAPI parses JSON. The server never truncates client history or accepts client
model, prompt, temperature, retrieval, token, or cost overrides.

The successful SSE sequence remains `start`, one or more `delta`, then `complete`. A timeout or
provider failure after streaming begins emits exactly one terminal `error` and never `complete`:

```text
event: error
data: {"code":"request_timed_out","message":"The response could not be completed."}
```

Closing or aborting the response closes the request-local event iterator and provider stream, then
idempotently releases both concurrency slots. Starlette's streaming response awaits each write and
does not build an unbounded response queue. The overall request/provider timeouts bound stalled
streams; the provider's native request timeout is set to the smaller remaining overall/first-token
budget for initial streaming work.

### Stable pre-stream errors

| Status | `detail.code` | Widget behavior |
| --- | --- | --- |
| 400 | `invalid_request` | Correct malformed JSON/framing; do not retry unchanged input |
| 403 | `origin_not_allowed` | Do not retry from this deployment origin |
| 404 | `assistant_not_found` | Assistant is absent or not publicly available |
| 413 | `request_too_large` | Reduce the encoded request |
| 415 | `unsupported_media_type` | Send JSON with the required content type |
| 422 | `validation_error` | Correct request/history shape |
| 422 | `message_too_long` | Reduce the current message |
| 422 | `history_too_large` | Reduce prior complete turns |
| 422 | `too_many_history_messages` | Remove oldest complete turns |
| 422 | `input_token_limit_exceeded` | Reduce prompt/history input |
| 429 | `rate_limit_exceeded` | Honor `Retry-After` when present |
| 429 | `client_concurrency_limit_exceeded` | Wait for the active request to finish |
| 503 | `global_concurrency_limit_exceeded` | Retry with short backoff |
| 503 | `public_chat_unavailable` | Route gate/protection storage is unavailable |
| 504 | `request_timed_out` | Offer a deliberate retry |

Streaming also uses `generation_failed` and `request_timed_out`. The browser should use an
`AbortController` on navigation, refresh, or user cancellation and treat an aborted stream as
cancelled rather than completed. No cookie or `credentials: include` setting is required.

## Enforcement architecture

Low-cost protection order is: gate, framework client-address resolution, origin, content type, raw
bytes, JSON/schema limits, layered rate limits, per-client slot, global slot, assistant validation,
retrieval/prompt budget, generation, then guaranteed cleanup. Rejected requests do not embed,
retrieve, query the assistant repository, or invoke the model.

Uvicorn is the only component allowed to interpret forwarding headers. In production,
`FORWARDED_ALLOW_IPS` must exactly match `PUBLIC_CHAT_TRUSTED_PROXIES`; application code hashes
`request.client.host` with HMAC-SHA256 and never trusts raw `X-Forwarded-For`. Configure only the
hosting platform's known proxy CIDRs. Direct forged forwarding headers are ignored.

Per-minute, per-hour, and deployment-global request counters use the established `limits` library.
Production/staging use Redis and fail closed with `public_chat_unavailable` when the store fails;
development/tests use explicit in-process storage. Distributed concurrency uses redis-py's owned,
expiring lock slots, acquired per-client then globally with immediate rejection and no request
queue. A failed global acquisition immediately releases the client slot; release is idempotent.

Retrieved chunks stay in relevance order and only complete chunks fitting both context count and
conservative context budgets are retained. The prompt estimator counts UTF-8 bytes plus
message-format overhead; this deliberately overestimates ordinary provider tokenisation when no
official tokenizer is bundled. It includes system instructions, selected knowledge, history,
current input, format overhead, and a reserved output budget. The provider always receives the
server-owned output cap.

Only `gpt-5.5` and its pinned `gpt-5.5-2026-04-23` snapshot are currently approved. Versioned
metadata records a 1,050,000-token context limit and standard text prices of $5/M input and $30/M
output; configuration validates maximum exposure without network pricing calls. Update and review
this metadata before approving another model or pricing change.

## Configuration

All values below are required explicitly when the route is enabled in production. Development/test
defaults match `.env.example`; they are finite and are not production fallbacks.

| Variable | Development default | Purpose |
| --- | ---: | --- |
| `PUBLIC_ASSISTANT_CHAT_ENABLED` | `false` | Deployment gate |
| `PUBLIC_CHAT_ALLOWED_ORIGINS` | `http://localhost:5173` | Exact comma-separated origins |
| `PUBLIC_CHAT_TRUSTED_PROXIES` | empty | Known proxy CIDRs |
| `FORWARDED_ALLOW_IPS` | external | Must exactly match trusted proxies |
| `PUBLIC_CHAT_CLIENT_KEY_HASH_SECRET` | development-only value | HMAC key; production minimum 32 chars |
| `PUBLIC_CHAT_RATE_LIMIT_PER_MINUTE` | `10` | Per-IP burst limit |
| `PUBLIC_CHAT_RATE_LIMIT_PER_HOUR` | `100` | Per-IP sustained limit |
| `PUBLIC_CHAT_GLOBAL_RATE_LIMIT_PER_MINUTE` | `300` | Deployment safety limit |
| `PUBLIC_CHAT_MAX_CONCURRENT_REQUESTS_PER_CLIENT` | `2` | Active requests per resolved IP |
| `PUBLIC_CHAT_MAX_CONCURRENT_REQUESTS_GLOBAL` | `20` | Deployment active request slots |
| `PUBLIC_CHAT_MAX_REQUEST_BYTES` | `32768` | Raw encoded body bytes |
| `PUBLIC_CHAT_MAX_MESSAGE_CHARACTERS` | `4000` | Current message characters |
| `PUBLIC_CHAT_MAX_HISTORY_MESSAGE_CHARACTERS` | `4000` | One history item |
| `PUBLIC_CHAT_MAX_HISTORY_MESSAGES` | `12` | Even count of completed-turn messages |
| `PUBLIC_CHAT_MAX_HISTORY_CHARACTERS` | `12000` | Aggregate history characters |
| `PUBLIC_CHAT_MAX_HISTORY_TOKENS` | `12000` | Conservative aggregate estimate |
| `PUBLIC_CHAT_MAX_INPUT_TOKENS` | `8000` | Complete prompt estimate |
| `PUBLIC_CHAT_MAX_CONTEXT_CHUNKS` | `3` | Selected retrieved chunks |
| `PUBLIC_CHAT_MAX_CONTEXT_TOKENS` | `4000` | Retrieved-content estimate |
| `PUBLIC_CHAT_MODEL_CONTEXT_TOKENS` | `1050000` | Reviewed provider context metadata |
| `PUBLIC_CHAT_MAX_OUTPUT_TOKENS` | `500` | Hard provider output cap |
| `PUBLIC_CHAT_MAX_ESTIMATED_COST` | `0.10` | Maximum USD input/output exposure |
| `PUBLIC_CHAT_REQUEST_TIMEOUT_SECONDS` | `45` | Overall operation/stream deadline |
| `PUBLIC_CHAT_MODEL_FIRST_TOKEN_TIMEOUT_SECONDS` | `15` | Initial provider stream deadline |
| `PUBLIC_CHAT_RETRIEVAL_LIMIT` | `3` | Candidate retrieval count |
| `PUBLIC_CHAT_MIN_SIMILARITY_SCORE` | `0.7` | Eligible similarity floor |
| `PUBLIC_CHAT_TEMPERATURE` | `0.2` | Server-owned generation temperature |
| `REDIS_URL` | local Redis | Shared rate/concurrency storage |

Metrics cover rate/origin/payload/input/concurrency rejections, timeouts, cancellation, active
requests, request bytes, estimated input, retrieval/generation/total duration, and completion.
Labels are bounded reasons only. Logs contain safe request/assistant identifiers, hashed client
keys where needed, bounded counts, selected internal chunk IDs, model, budgets, and outcome—not
messages, histories, prompts, session IDs, Redis keys, credentials, or provider payloads.

## Controlled load tests

The load harness uses Locust and `load_tests.fake_app`, whose deterministic provider never calls a
paid model. It supports first-token delay, token delay, output length, and controlled provider
failure. Install the pinned load-only dependency and start it from `apps/backend`:

```sh
venv/bin/python -m pip install -r load_tests/requirements.txt
PUBLIC_CHAT_RATE_LIMIT_PER_MINUTE=10000 \
PUBLIC_CHAT_RATE_LIMIT_PER_HOUR=10000 \
PUBLIC_CHAT_GLOBAL_RATE_LIMIT_PER_MINUTE=10000 \
venv/bin/python -m uvicorn load_tests.fake_app:app --port 8011
```

Run repeatable scenarios in another shell:

```sh
LOAD_SCENARIO=baseline venv/bin/locust -f load_tests/locustfile.py --headless -u 2 -r 2 -t 15s --host http://127.0.0.1:8011
LOAD_SCENARIO=burst venv/bin/locust -f load_tests/locustfile.py --headless -u 40 -r 40 -t 15s --host http://127.0.0.1:8011
LOAD_SCENARIO=concurrency venv/bin/locust -f load_tests/locustfile.py --headless -u 30 -r 30 -t 15s --host http://127.0.0.1:8011
LOAD_SCENARIO=slow venv/bin/locust -f load_tests/locustfile.py --headless -u 4 -r 4 -t 15s --host http://127.0.0.1:8011
LOAD_SCENARIO=disconnect venv/bin/locust -f load_tests/locustfile.py --headless -u 20 -r 20 -t 15s --host http://127.0.0.1:8011
LOAD_SCENARIO=oversized venv/bin/locust -f load_tests/locustfile.py --headless -u 10 -r 10 -t 10s --host http://127.0.0.1:8011
```

For slow-model behavior, set `LOAD_TEST_FIRST_TOKEN_DELAY_SECONDS`,
`LOAD_TEST_TOKEN_DELAY_SECONDS`, and `LOAD_TEST_OUTPUT_CHUNKS` on the fake server. Record Locust's
request count, failure/rejection rate, p50/p95/p99 latency, and throughput together with process
memory and `/metrics` active/time-to-first-token/timeout counters. Acceptance is behavioral rather
than an invented throughput number: below-limit baseline streams complete without leaks; overload
is bounded by documented 429/503 responses; timeout/disconnect/oversize scenarios recover active
slots to zero; process memory has no sustained post-scenario growth; Redis/database errors remain
zero in the controlled fake environment.

## Production-enablement checklist

- PR 11C and PR 11D are merged and the route is enabled explicitly.
- Exact production origins and known proxy CIDRs are configured; forwarded headers are verified on
  the hosting platform with direct and proxied tests.
- Redis is shared across every replica, healthy, monitored, and public-chat readiness is verified.
- Request, history, input, context, output, cost, rate, concurrency, and timeout values are reviewed.
- The approved model metadata and provider account quotas match the deployment.
- Provider cancellation, timeout, browser abort, and permit recovery tests pass in staging.
- Baseline, burst, saturation, slow-model, disconnect, and oversized load scenarios are recorded for
  staging; active requests return to zero and memory has no sustained growth.
- Dashboards and alerts cover rejection reasons, timeouts, provider failures, Redis errors, active
  concurrency, latency, and output usage.

Do not enable the production route until every item is satisfied. Keep edge protection available as
an additional layer; it does not replace application enforcement.
