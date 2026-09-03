# @redmoor/assistant-widget

## 0.3.0

### Minor Changes

- db41f1d: Removed obsolete widget legacy client and generated types.

## 0.2.0

### Minor Changes

- e9e2942: Load and validate published Assistant presentation configuration before rendering the public widget,
  while preserving optional presentation props as explicit overrides.

### Patch Changes

- 6913bc6: Document the pull-request paths that run assistant widget validation.
- b95d1cf: Make the Assistant widget pull-request check appear only when the full validation pipeline runs and
  verify its path-scoping and quality-gate configuration.

## 0.1.1

### Patch Changes

- 714c58f: Make Release PR validation compatible with consumed Changesets and document reliable workflow recovery.
- f5d7a14: Separate the reusable widget package from its development demo and adopt Changesets releases.
