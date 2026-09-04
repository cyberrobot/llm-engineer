# Admin Engineering Rules

## Navigation and architecture

Start at the narrowest boundary: a page or feature in `src/features/`, reusable UI in `src/components/`, backend communication in `src/api/`, or administrator session behaviour in `src/auth/`. Inspect `src/routing.ts` or `src/App.tsx` only when routing or application composition changes.

```text
UI / feature
    ↓
API/auth client boundary
    ↓
backend HTTP contract
```

Browser code must not import backend implementation, access persistence, duplicate server authorization or business rules, or bypass established API clients. The backend remains authoritative.

## React, styling, and tests

Use existing TypeScript and React patterns, semantic accessible UI, deliberate state ownership, routing abstractions, and existing components before creating another. Use the established Tailwind styling setup; do not add another styling framework, parallel design system, or speculative generic components.

Test user-visible outcomes through rendered interactions rather than component internals. Follow repository browser and visual-test infrastructure when rendered behaviour materially changes.

## Verification

Run focused checks first, then the relevant commands from the repository root:

```sh
npm run lint --workspace @ai-discovery-assistant/admin
npm run typecheck --workspace @ai-discovery-assistant/admin
npm test --workspace @ai-discovery-assistant/admin
npm run build --workspace @ai-discovery-assistant/admin
npm run build-storybook --workspace @ai-discovery-assistant/admin
```
