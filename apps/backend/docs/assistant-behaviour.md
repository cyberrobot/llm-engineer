# Assistant behaviour, publishing, and preview

Assistant behaviour is persisted as immutable, Assistant-owned revisions. Phase 1 supports four
validated fields: `instructions`, `welcome_message`, `input_placeholder`, and the ordered
`suggested_questions` list. Provider/model and generation parameters are deliberately not editable.
An empty `welcome_message` explicitly means that the client should show no welcome message;
instructions and the one-line input placeholder must remain non-empty.

Each Assistant has one current draft pointer and zero or one published pointer. Existing Assistants
are migrated to canonical revision 1 and that revision is published. New Assistants are created with
the same published default in the transaction that creates the inactive/private Assistant. This
keeps existing public Assistants usable and gives new Assistants deterministic configuration without
exposing them.

The administrator contract is:

- `GET /admin/assistants/{id}/behaviour` returns the editable draft, published metadata,
  `has_unpublished_changes`, and an opaque concurrency token.
- `PUT /admin/assistants/{id}/behaviour` replaces the complete draft. It requires the latest token,
  returns the authoritative next state, and returns
  `assistant_behaviour_update_conflict` for a stale token. An identical save is a no-op.
- `POST /admin/assistants/{id}/behaviour/publish` requires both the latest token and exact current
  draft revision. A stale or superseded draft returns `assistant_behaviour_publish_conflict`.
  Publishing the already-published current draft is idempotent.
- `POST /admin/assistants/{id}/preview/chat` streams the same `start`, `delta`, `complete`, and
  `error` SSE event shapes as public chat, but uses the saved current draft. It accepts the same
  bounded message/history shape and works for inactive or private Assistants.

Draft revision metadata exposes only `created_at`. Revisions are immutable, so publishing a draft
or otherwise changing publication state never changes that revision-owned timestamp.

All routes require the existing administrator cookie session. Save, publish, and preview also
require the configured trusted administrator origin. Preview requests cannot supply arbitrary
instructions and do not store conversation state.

## Independent lifecycle concepts

Saving is not publishing. Previewing is not publishing. Publishing is not activating. Publishing
does not make an Assistant public. Public chat still requires both `status=active` and
`visibility=public`, and it resolves the published revision exactly once per request. A later draft
therefore cannot affect public requests until it is explicitly published.

## Prompt hierarchy and privacy

The provider system prompt always begins with platform-owned grounding and security rules. Those
rules require evidence, treat retrieval/history/user content as untrusted data, reject embedded
instructions, and prohibit disclosure of hidden configuration or reasoning. Administrator-authored
instructions are JSON-encoded inside a clearly delimited subordinate section after the platform
rules. Retrieved knowledge, history, and the current message remain JSON-encoded in separate
untrusted sections. Configurable instructions cannot replace the platform rules or bypass the fixed
insufficient-knowledge response.

Instructions and preview content are sensitive. Logs contain only safe identifiers, revision
numbers, bounded outcomes, and existing operational metadata; request bodies, prompt content,
knowledge chunks, conversation history, provider payloads, and full generated responses are not
logged. Metrics use only bounded operation/outcome labels.

## Persistence guarantees

`assistant_behaviour_revisions` uses `(assistant_id, revision)` as its identity and rejects updates
with a database trigger. `assistant_behaviour_states` points to revisions using composite foreign
keys, preventing cross-Assistant draft or publication pointers. Saves and publishes lock and update
one state row transactionally. Assistant deletion cascades only this exclusively owned behaviour
state; existing knowledge-dependency deletion safeguards remain unchanged.
