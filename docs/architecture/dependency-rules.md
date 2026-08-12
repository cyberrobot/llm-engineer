# Dependency Rules

This document defines the allowed dependency directions within the Redmoor monorepo.

Violations should be treated as architecture issues, not implementation preferences.

---

# High-level architecture

```text
Frontend
    │
    ▼
API Layer
    │
    ▼
Application Services
    │
    ▼
Domain
    │
    ▼
Persistence
```

Dependencies flow downwards only.

Lower layers must never depend on higher layers.

---

# Backend

## API

Responsible for:

- HTTP routing
- Authentication
- Request validation
- Response mapping
- Status codes

May depend on:

- Application services
- Domain models

Must NOT depend on:

- Database implementation details
- Infrastructure concerns

---

## Application Services

Responsible for:

- Business orchestration
- Transactions
- Calling repositories
- Calling external services
- Domain coordination

May depend on:

- Domain
- Persistence interfaces
- Infrastructure adapters

Must NOT depend on:

- FastAPI
- HTTP request/response objects
- Frontend models

---

## Domain

Responsible for:

- Business rules
- Validation
- Entities
- Value objects

May depend on:

- Standard library

Must NOT depend on:

- FastAPI
- SQLAlchemy
- PostgreSQL
- Redis
- OpenAI
- HTTP
- Infrastructure

The domain should be portable.

---

## Persistence

Responsible for:

- Database access
- Queries
- Transactions
- Mapping rows to domain models

May depend on:

- SQLAlchemy
- PostgreSQL
- Domain models

Must NOT contain:

- Business rules
- HTTP logic

---

# AI Retrieval

Retrieval orchestration belongs in:

apps/backend/app/services/retrieval/

Embedding providers belong in:

apps/backend/app/infrastructure/embeddings/

Vector database implementation belongs in:

apps/backend/app/persistence/vector/

Business logic must never know:

- pgvector
- embedding model names
- OpenAI API details

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
