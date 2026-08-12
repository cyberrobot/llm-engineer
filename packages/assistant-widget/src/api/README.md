# Assistant API

This directory contains the Assistant HTTP integration:

- `assistant.ts` exposes the typed Assistant operations.
- `client.ts` centralises HTTP behavior and error handling.
- `types/schema.ts` contains types generated from the backend OpenAPI document.

The backend OpenAPI document remains the source of truth for request and response shapes.
