Testing Instructions

Core Principle

Tests must verify externally observable behaviour and business rules, not merely mirror the current implementation.

A test suite is only valuable if it would fail when realistic defects are introduced.

Do not write tests solely to increase coverage or make the current implementation appear correct.

Required Development Process

For every feature change or bug fix:

1. Inspect the existing implementation and relevant tests.
2. Identify the expected behaviour, invariants, failure modes, and security boundaries.
3. Add or update tests before changing production code where practical.
4. Run the new tests and confirm they fail for the expected reason.
5. Implement the smallest production change required.
6. Run the targeted tests.
7. Run the broader relevant test suite.
8. Run type checking and linting.
9. Review whether the tests would catch realistic implementation defects.

Do not weaken tests to make an implementation pass.

Do not change expected behaviour merely to match the current implementation.

Test Behaviour, Not Implementation Details

Prefer testing through public interfaces such as:

- API endpoints
- exported functions
- public service methods
- rendered user interactions
- database state
- persisted files
- observable side effects

Avoid testing:

- private functions directly
- internal variable values
- exact internal call order
- internal component structure
- implementation-specific helper methods
- whether a mock was called without verifying the resulting behaviour

Refactoring internal code should not break tests when externally observable behaviour remains unchanged.

Mocking Rules

Do not mock the unit under test.

Avoid mocking internal application layers when a realistic integration test can exercise them.

Use real implementations where practical for:

- request validation
- authentication and authorisation middleware
- route handlers
- service logic
- repositories
- serializers
- database queries
- database constraints
- transactions
- migrations
- file validation
- state management
- application components

Mock only true external boundaries, such as:

- email providers
- SMS providers
- payment providers
- malware scanning services
- cloud object storage
- third-party APIs
- operating-system integrations that cannot run in the test environment

Mocks must behave realistically, including expected failures.

Do not over-specify mocks in a way that causes tests to pass only because the mock reproduces the implementation.

Database Testing

Integration tests should use a real disposable test database where practical.

Tests involving persistence must verify:

- the API or function result
- the final database state
- the absence of unintended records
- ownership and access restrictions
- transaction behaviour
- rollback after failure
- database constraints
- state after reloading from the database

Do not rely only on repository method assertions.

Run database migrations against the test database rather than manually recreating an approximate schema.

Tests must not depend on execution order or shared mutable state.

Each test must create or reset its own required data.

Required Test Coverage

Cover the following where applicable:

Happy paths

Verify expected behaviour for valid requests and normal user journeys.

Invalid input

Test:

- missing required fields
- malformed values
- incorrect types
- invalid formats
- unsupported values
- values outside allowed limits
- empty values
- unexpected additional fields

Authentication and authorisation

Test:

- unauthenticated access
- expired or invalid credentials
- insufficient permissions
- access to another user’s data
- access to deleted, archived, or unavailable resources
- privilege escalation attempts

Never assume authentication automatically guarantees ownership.

Boundary conditions

Test:

- minimum values
- maximum values
- values immediately below and above limits
- empty collections
- single-item collections
- large collections
- null or undefined values where relevant

Duplicate and repeated requests

Test:

- duplicate submissions
- repeated button presses
- retried API requests
- idempotency where required
- duplicate records
- repeated updates
- stale client requests

Failure paths

Test realistic failures such as:

- database failure
- storage failure
- network failure
- external service timeout
- malformed external response
- partial completion
- transaction rollback
- interrupted upload
- retry exhaustion

Concurrency

Where race conditions are possible, test concurrent operations such as:

- two requests creating the same resource
- two requests updating the same record
- two requests attempting to create a unique active record
- deletion while another operation is in progress
- duplicate file uploads
- stale updates overwriting newer changes

Do not rely solely on application-level checks when a database constraint is appropriate.

Persistence

For flows involving drafts, forms, edits, uploads, or saved progress, verify that:

- data remains correct after reload
- editing does not create duplicate records
- omitted update fields are not unintentionally reset
- immutable fields remain unchanged
- state transitions are valid
- incomplete operations do not leave inconsistent state

Regression Tests

Every bug fix must include a regression test that:

- reproduces the original defect
- fails before the fix
- passes after the fix
- verifies the underlying behaviour rather than the specific implementation

Name regression tests clearly so the protected behaviour is obvious.

Do not fix a bug without adding a test unless testing is genuinely impossible. Document the reason if no automated test can be added.

Security-Sensitive Tests

Security controls must be tested directly.

Where applicable, verify:

- users can access only their own records
- organisation boundaries are enforced
- server-side validation cannot be bypassed
- deleted resources cannot still be retrieved
- identifiers cannot be guessed to access other records
- sensitive data is not exposed in error responses
- audit events are recorded correctly
- unauthorised actions produce no side effects
- file metadata cannot bypass content validation
- filenames cannot cause path traversal
- upload limits are enforced
- content type and file signatures are validated
- database records are not created when file storage fails
- stored files are removed or reconciled when database writes fail

A successful status code alone is not sufficient evidence that a security rule works.

Assertion Quality

Use precise, business-relevant assertions.

Prefer assertions that verify:

- exact status or result type
- relevant response fields
- persisted values
- ownership
- record counts
- state transitions
- timestamps where important
- unchanged immutable values
- emitted events
- absence of unintended side effects
- user-visible output

Avoid assertions that only verify:

- truthiness
- that no exception occurred
- object existence
- a mock being called
- a response status without checking state
- broad snapshots without meaningful semantic assertions

Snapshots may supplement explicit assertions but must not replace them.

Mutation-Oriented Review

Before completing a task, consider realistic defects that could be introduced into the production code.

Examples:

- remove an ownership filter
- reverse a comparison operator
- remove validation
- skip a transaction
- create a new record instead of updating an existing one
- omit a database constraint
- return hard-coded data
- ignore an external service failure
- reset fields not included in an update
- permit an invalid state transition

Confirm that at least one test would fail for each relevant defect.

Strengthen the tests when a plausible bug could be introduced without causing a failure.

Frontend and UI Tests

Frontend tests should prioritise user behaviour.

Prefer queries based on:

- accessible role
- label
- visible text
- accessible name
- user-facing state

Avoid querying by:

- CSS class
- internal component name
- implementation-specific test IDs when an accessible query is available
- DOM structure that users do not depend on

Simulate realistic user interactions rather than calling component handlers directly.

Verify:

- loading states
- empty states
- validation messages
- error states
- disabled states
- retries
- navigation
- persisted form state
- duplicate click handling
- keyboard interaction
- accessibility behaviour
- successful and failed submissions

Do not mock the entire application layer in a way that makes the UI test meaningless.

End-to-End Tests

Add end-to-end tests for critical user journeys and high-risk behaviour.

End-to-end tests should cover a small number of valuable flows rather than duplicating every unit or integration test.

Prioritise:

- authentication
- incident creation and editing
- draft recovery
- evidence and attachment handling
- ownership and access restrictions
- critical state transitions
- deletion and recovery behaviour
- export or download flows
- failure recovery

End-to-end tests must verify the final user-visible and persisted outcome.

Test Data

Use realistic but fictional test data.

Do not use:

- production data
- real access tokens
- real credentials
- real personal information
- fixed IDs that may collide across tests

Create reusable test factories where they improve clarity.

Factories should produce valid defaults while allowing individual fields to be overridden.

Avoid large fixtures containing irrelevant data.

Test Isolation

Tests must be deterministic and independently executable.

Do not depend on:

- test execution order
- another test creating data
- real network access
- current production state
- uncontrolled system time
- random behaviour without a fixed seed
- shared mutable mocks

Freeze or control time where time-dependent behaviour is being tested.

Clean up temporary files, database records, timers, and mocks after tests.

Test Naming

Test names must describe:

- the scenario
- the action
- the expected outcome

Prefer:

rejects access when a user requests another user's incident

Avoid:

works correctly

A reader should understand the protected behaviour without reading the implementation.

Prohibited Actions

Never:

- delete an existing test solely because it fails after a change
- skip or disable a failing test without documenting a valid reason
- loosen an assertion merely to make the test pass
- replace a meaningful assertion with a snapshot
- mock away the behaviour being tested
- alter production code exclusively for test convenience when a better test setup is possible
- commit focused tests such as .only
- leave skipped tests without an explanation
- hide test failures
- claim tests passed without running them

If an existing test appears incorrect, explain why and update it only when the intended behaviour has been confirmed.

Required Commands

Before completing a task, run the relevant project commands for:

- targeted tests
- integration tests
- the broader relevant test suite
- type checking
- linting

Use the commands defined by the repository.

Do not claim a command succeeded unless it was actually run successfully.

If a command cannot be run, report:

- the command
- the reason
- the observed error
- the remaining risk

Completion Report

When completing an implementation task, report:

1. Behaviour covered
2. Tests added or updated
3. Initial failing test result
4. Production changes made
5. Commands run
6. Final test results
7. Remaining gaps or risks

Do not state that the implementation is complete while relevant tests are failing.

Definition of Done

A change is complete only when:

- expected behaviour is defined
- relevant tests exist
- new tests were shown to fail before the fix where practical
- the implementation passes the tests
- regression risks are covered
- security and ownership boundaries are tested
- persistence and unintended side effects are verified
- targeted and broader tests pass
- type checking passes
- linting passes
- remaining limitations are explicitly documented

GitHub Authentication and Pull Requests

GitHub authentication checks run inside a restricted execution environment may not be able to
read credentials stored in the host keychain. A failed sandboxed `gh auth status` does not
necessarily mean the user is logged out.

When creating a new branch, always fetch the latest remote state first and create the branch from
the up-to-date `origin/main`, not from a potentially stale local `main` or the current branch. Use
`git switch --no-track -c <branch-name> origin/main` so the new feature branch does not inherit
`origin/main` as its upstream. Never configure a feature branch to track the remote default branch.
On its first push, publish it with `git push --set-upstream origin <branch-name>` and verify that the
local branch now tracks the same-named remote feature branch. This avoids a plain push being rejected
by Git's `simple` push mode and prevents accidental pushes to `main`.

Before asking the user to authenticate again:

1. Re-run `gh auth status` outside the restricted environment with the required approval.
2. Confirm repository access with `gh repo view --json nameWithOwner,defaultBranchRef` in the same
   environment.
3. Ask the user to run `gh auth login` only if the host-level authentication check also fails.

When the user requests commit, push, and pull-request creation:

1. Inspect `git status -sb` and the diff before staging.
2. Stage only files that belong to the requested change. Do not include unrelated or untracked
   files without confirmation.
3. Commit with a concise description of the complete change.
4. Push the current feature branch to a same-named remote branch with upstream tracking. If its
   upstream is currently the default branch, correct it with
   `git push --set-upstream origin <branch-name>`; never resolve the mismatch by pushing the feature
   commit to the default branch.
5. Create a draft pull request against the repository's default branch unless the user explicitly
   requests a ready-for-review pull request or a different base branch.
6. Use a Markdown body with real newlines that describes the change, its impact, and the validation
   commands that actually passed.
7. Verify and report the branch, commit, base branch, PR URL, draft status, and any files deliberately
   left uncommitted.

# Library Reuse

## Guiding Principle

Prefer mature, well-maintained, existing libraries over custom implementations whenever they are suitable for the problem.

The goal is to minimise maintenance burden, reduce bugs, improve reliability, and keep the codebase focused on business logic rather than reimplementing solved problems.

---

## Before Writing Code

Before implementing any new functionality, always:

1. Inspect the existing project dependencies.
2. Inspect the existing codebase for reusable utilities or abstractions.
3. Reuse existing libraries where they already solve the problem.
4. Extend existing implementations instead of creating parallel ones.
5. Introduce a new dependency only when there is a clear technical benefit that cannot reasonably be achieved using the current stack.

Avoid creating duplicate functionality.

---

## Preferred Order

Always follow this order of preference:

1. Python Standard Library
2. Existing project libraries
3. Existing project utilities
4. Well-maintained third-party libraries
5. Custom implementation (only if necessary)

Custom code should be the last resort, not the default.

---

## Do Not Reinvent Existing Solutions

Avoid writing custom implementations for capabilities that are already well solved by established libraries.

Examples include:

- HTML parsing
- HTTP clients
- URL parsing and validation
- Configuration management
- Logging
- Dependency injection
- Database access
- Migrations
- Tokenisation
- Text splitting
- Retry strategies
- Date and time handling
- Hashing
- Validation
- Serialization
- UUID generation
- Markdown parsing
- Sitemap parsing
- Robots.txt parsing

Use existing libraries whenever they satisfy the project's requirements.

---

## Reuse Existing Project Libraries

Before introducing a new dependency, inspect the project's existing dependencies.

For example:

- If BeautifulSoup or Selectolax is already installed, reuse it.
- If HTTPX is already used, continue using HTTPX.
- If Pydantic already performs validation, do not introduce another validation library.
- If SQLAlchemy is used, do not introduce another ORM.
- If Alembic is used, continue using Alembic migrations.
- If a tokenizer already exists in the project, reuse it rather than creating another implementation.

Avoid multiple libraries solving the same problem.

---

## New Dependencies

A new dependency may be introduced only if:

- the existing stack cannot reasonably solve the problem
- the library is mature and actively maintained
- it has a permissive licence compatible with the project
- it provides a clear improvement over writing custom code
- it does not duplicate existing functionality

Document the reason for introducing any new dependency.

---

## Extend Existing Abstractions

When adding new functionality:

- extend existing services
- extend existing repositories
- extend existing ports/interfaces
- extend existing configuration
- extend existing dependency injection

Do not create parallel abstractions simply because they are convenient.

---

## Consistency

When multiple libraries could solve the problem equally well, prefer the one already used by the project.

Consistency across the codebase is more valuable than using the newest or most popular library.

---

## Goal

Spend engineering effort solving business problems, not rebuilding infrastructure that already exists.

Every custom implementation increases long-term maintenance cost. Prefer proven libraries and existing project abstractions whenever they meet the project's needs.
