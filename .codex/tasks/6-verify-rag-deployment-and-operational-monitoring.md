# PR 6 — Verify RAG deployment and operational monitoring

## Repository state

Expected branch:

`6-verify-rag-deployment-and-operational-monitoring`

Base branch:

`main`, after PR #99 has merged.

Worktree:

Fresh worktree based on current `origin/main`.

Dependencies:

- PR #99 / PR 5 repository implementation must be present.
- Access to the actual RAG deployment, monitoring workspace, alert configuration, notification
  destination, and staging rollback controls is required.
- Production RAG routing must remain unchanged unless separately authorized.

### Read first

- `AGENTS.md`
- `.codex/tasks/5-establish-database-and-operational-ownership.md`
- `apps/rag-backend/OPERATIONS.md`
- `apps/rag-backend/README.md`
- `apps/backend/docs/rag-persistence-contract.md`

### Primary change area

- deployment-managed RAG service settings;
- the established monitoring/dashboard and alerting system;
- staging deployment and rollback controls;
- operational verification records and narrowly scoped documentation corrections.

### Canonical implementation examples

- `apps/rag-backend/Dockerfile`
- `apps/rag-backend/OPERATIONS.md`
- `apps/rag-backend/.env.example`
- deployment and monitoring records for the independently deployed RAG service.

### Relevant symbols

- `rag-backend`
- `/health/live`
- `/health/ready`
- `RAG Backend Operations`
- `http_request_completed`
- `provider_request_completed`
- `retrieval_failed`
- `rate_limit_rejected`
- `audit_write_failed`
- `readiness_check_failed`

### Expected change surface

- deployment-platform configuration;
- monitoring dashboards and alert rules;
- notification test evidence;
- staging rollback exercise evidence;
- final operational owner and location documentation.

Repository changes should be limited to truthful operational documentation or deployment-as-code
that uses the existing platform. Do not change application behaviour to simulate external evidence.

### Excluded areas

Do not:

- change application code, database ownership, migrations, telemetry schemas, API contracts,
  authorization, maintenance, caching, retrieval, or Admin behaviour;
- introduce a new monitoring vendor or parallel observability stack;
- route production RAG traffic to the standalone service without separate authorization;
- use destructive database rollback or remove RAG or legacy audit data;
- store credentials, tokens, database URLs, or sensitive infrastructure data in the repository.

### Unknowns Codex must verify

1. Which Railway or equivalent project, environment, and service host the standalone RAG service.
2. Whether that service is deployed independently from `apps/backend`.
3. Which monitoring workspace receives `service="rag-backend"` telemetry.
4. Who owns the service, dashboard, alert rules, notification destination, and rollback procedure.
5. Whether standalone RAG routing is enabled in staging and absent from production.
6. Which previous known-good RAG image/version is safe to select during the staging exercise.

GitHub deployment records currently show repository deployments to a Railway production environment,
but they do not identify an independently deployed RAG service or prove any health-check, monitoring,
alert, notification, telemetry, or rollback criterion. Treat those records only as a discovery lead.

---

## Objective

Complete the environment-dependent operational acceptance work deferred from PR 5 by verifying the
real standalone RAG deployment, installing or confirming its dashboard and alerts, testing safe
notification delivery, and exercising the rollback runbook in staging without affecting production
traffic or persisted data.

## Current architecture

PR #99 supplies the independent RAG image, least-privilege PostgreSQL topology, RAG-owned audit
migrations, backend-owned maintenance integration, liveness/readiness endpoints, safe structured
telemetry, dashboard query definitions, alert thresholds, deployment ordering, and rollback runbook.

The repository does not contain a Railway service manifest, gateway configuration,
monitoring-as-code, alert installation, a staging endpoint, or deployment credentials. Those facts
must be discovered and verified in the deployment-managed environment. Documentation is not proof
that the corresponding configuration has been installed.

## Required implementation

### Verify the independent deployment

Identify and record the deployment platform, project, environment, service name, service owner, and
currently deployed image/version. Confirm that the service runs `apps/rag-backend` independently of
`apps/backend`, uses `/health/ready` as its traffic health check, and has no migration credential in
its normal runtime configuration.

Against staging, verify `/health/live` is healthy and dependency-free and `/health/ready` is healthy
when its required PostgreSQL and enabled Redis dependencies are available. Confirm production RAG
traffic has not moved to this service without separate authorization.

### Install or verify operational monitoring

In the established monitoring workspace, install or verify dashboard **RAG Backend Operations**,
filtered to `service="rag-backend"`, with:

1. request volume and status distribution;
2. `/rag-chat` p50/p95/p99 latency;
3. provider failure/timeout rate calculated as failed or timed-out `provider_request_completed`
   events divided by all `provider_request_completed` events;
4. retrieval failure rate;
5. rate-limit rejection volume;
6. audit-write failures;
7. readiness failures and service availability.

Install or verify the alerts and minimum-volume conditions documented in
`apps/rag-backend/OPERATIONS.md`. Exercise at least one safe test-notification path and confirm its
delivery. Confirm real staging `rag-backend` telemetry appears in the dashboard; synthetic repository
tests are not sufficient evidence.

### Exercise staging rollback

Without changing production routing or rolling back database migrations:

1. record the current staging RAG version and routing state;
2. remove or disable standalone staging RAG routing if it is enabled;
3. select or redeploy the previous known-good RAG image/version;
4. verify backend `/health/ready`, ingestion, administrator APIs, and maintenance control remain
   healthy;
5. verify the documented RAG credential revocation/disable procedure without exposing secrets;
6. restore the original staging RAG version and routing state;
7. verify RAG and legacy audit data remain intact.

Record exactly which steps were exercised, their results, timestamps, and any safe evidence links.
If a step cannot be performed, leave its criterion open and explain the concrete access or safety
constraint.

### Record operational evidence

Document, without secrets:

- dashboard name and location;
- deployment project/environment/service and current version;
- dashboard queries and service filter;
- alert names, queries, thresholds, evaluation windows, and minimum event counts;
- operational owner and notification destination owner;
- successful health, telemetry, notification, and rollback verification evidence;
- confirmation that production routing and persisted audit data were not changed.

## Acceptance criteria

- [ ] The standalone `rag-backend` deployment is identified and proven independent of `apps/backend`.
- [ ] The deployed traffic health check is `/health/ready`.
- [ ] Staging `/health/live` and `/health/ready` return healthy results under normal dependencies.
- [ ] Production RAG routing remains unchanged unless separately authorized.
- [ ] Dashboard **RAG Backend Operations** exists in the established monitoring workspace.
- [ ] All seven required dashboard views are present and filtered to `service="rag-backend"`.
- [ ] Provider failures/timeouts are displayed as a true completion rate with the documented denominator.
- [ ] Real staging RAG telemetry is visible in the dashboard.
- [ ] All six documented alert classes are installed with their thresholds and minimum volumes.
- [ ] A safe test alert or notification is delivered successfully.
- [ ] The operational owner, dashboard location, service name, and alert ownership are recorded.
- [ ] The rollback runbook is exercised in staging and the original staging version is restored.
- [ ] Backend readiness, ingestion, administrator APIs, and maintenance controls remain healthy during the exercise.
- [ ] No destructive database rollback occurs and both RAG and legacy audit data are preserved.
- [ ] No production traffic cutover occurs without separate authorization.

## Tests to add or update

This is deployment verification, not an application-code task. Add repository tests only if a
deployment-as-code file is introduced or a documented command is found to be incorrect. Do not add
mocks or application tests as substitutes for live environment evidence.

Capture safe, reviewable evidence for service health, dashboard data, installed alerts, notification
delivery, and each exercised rollback step. Redact credentials, tokens, private URLs, raw payloads,
and sensitive infrastructure identifiers.

## Verification commands

Run repository checks only when repository files change, in addition to the live acceptance checks:

```bash
git diff --check
```

If implementation files change unexpectedly, stop and justify the scope before running and reporting
the full affected application suites from PR 5. Completion requires live environment evidence; local
or CI results alone cannot close this task.
