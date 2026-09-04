# Dependency Rules

These are architectural constraints, not implementation preferences.

## Backend direction

```text
API → application → domain
          ↓
 application-owned ports ← infrastructure adapters

composition/bootstrap → concrete implementations
```

- API owns routing, authentication, validation, and HTTP mapping. It depends on application services and transport-facing domain or application models where appropriate.
- Application services orchestrate domain rules and depend on application-owned ports. They should not normally depend on concrete infrastructure adapters, FastAPI, or frontend models.
- Domain owns business rules, validation, entities, and value objects. It is independent of FastAPI, databases, Redis, OpenAI, provider clients, environment configuration, and startup.
- Infrastructure implements application-owned ports and may map persistence or provider representations to application/domain models. Persistence adapters belong in infrastructure; Domain does not depend on persistence.
- Composition/bootstrap may know concrete implementations to construct the application. Lower-level modules must not import startup or composition roots.

For example, `assistant/application/ports/rag_knowledge_repository.py` is an application-owned RAG contract, while `assistant/infrastructure/repositories/rag_knowledge.py` provides its PostgreSQL adapter. Retrieval orchestration uses the port; it does not adopt PostgreSQL or provider details as its normal dependency surface.

---

# Frontend

React components

↓

Hooks

↓

API client

↓

Backend API

Components must never perform HTTP requests directly.

---

# Public widget package

packages/assistant-widget

Responsible for:

- React component API
- Type definitions
- Request models
- Response models
- Public backend transport

Must NOT:

- Depend on backend implementation
- Depend on demo or admin applications

---

# Widget

Widget components

↓

Conversation state

↓

Public chat client

↓

Backend

Widget components must not call fetch() directly.

---

# Admin

Admin pages

↓

Admin API client

↓

Backend

Admin components must not access repositories or database code.

---

# Cross-package rules

Allowed

apps/assistant-demo
↓
packages/assistant-widget

Allowed

apps/admin
↓
packages/assistant-widget

Not allowed

packages/assistant-widget
↓
apps/assistant-demo

Not allowed

packages/assistant-widget
↓
apps/admin

---

# Dependency inversion

When multiple modules require the same behaviour:

✓ Define an interface.

✓ Inject the implementation.

Avoid importing concrete implementations across domains.

---

# Events

Prefer events for:

- ingestion completion
- document processing
- assistant indexing

Avoid direct service-to-service coupling where asynchronous workflows already exist.

---

# External libraries

Prefer existing well-maintained libraries over custom implementations.

Do not introduce new libraries when an approved project dependency already provides equivalent functionality.

---

# Repository changes

Before introducing a new dependency:

1. Check whether an existing module already provides the capability.
2. Check repository-map.md.
3. Check architecture documents.
4. Reuse existing patterns.

Do not duplicate functionality.

---

# If these rules conflict

The dependency rules override implementation convenience.

If a feature cannot be implemented without violating these rules:

- stop;
- explain why;
- propose an architectural alternative.
