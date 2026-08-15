# Palguna Week 1 Parallel Implementation Plan

**Scope:** Palguna's work for the current Week 1 release only  
**Team model:** Palguna coordinates several Luna subagents; Akanksh develops his assigned modules separately  
**Merge target:** `week1/integration`, followed by one final pull request into `main`  
**Existing plan:** This file adds execution detail and does not replace `IMPLEMENTATION_PLAN.md`

## 1. Week 1 outcome

Palguna must deliver the shared product and the parts he owns around Akanksh's marketplace pipeline:

```text
Akanksh's published observations
        -> Palguna's shared API and web integration
        -> changes and assigned actions
        -> source and collection status
        -> operations, deployment, and release proof
```

The release is complete only when an approved setup can be viewed in the web app, a valid observation can create one change, that change can become an owned action, failures remain visible, and invalid data never appears as current data.

## 2. Scope boundaries

### Palguna builds now

- Shared API contracts, error handling, pagination helpers, audit actor, and access gate.
- Shared frontend shell, typed API client, common states, and cross-module navigation.
- Final integration of Akanksh's Universe, Keywords, Keyword Detail, Product Detail, and evidence surfaces.
- S4 Week 1 support: sponsored placement consumption and owned Amazon Ads synchronization.
- Amazon Ads API, Meta Marketing API, and supported Meta Ad Library adapters.
- S10 thin change-to-action flow.
- S11 Week 1 operations and in-app status only.
- Overview, Sources, Changes, Actions, and Operations screens.
- CI, deployment configuration, observability, runbooks, acceptance, and final integration.

### Palguna does not build now

- S7 review intelligence.
- S8 market-share or sales estimates.
- Full S9 scorecards.
- Full S11 war room, email, Slack, Teams, or BOS notifications.
- Competitor spend, bid, revenue, or sales estimates.
- Akanksh's collectors, parsers, marketplace rules, or module repositories.
- New marketplaces, devices, locations, or machine-learning features.

## 3. Files Palguna agents must not edit

These paths belong to Akanksh. A Palguna subagent may read them but must not change them:

```text
apps/backend/src/novel_signal/modules/universe/**
apps/backend/src/novel_signal/modules/keywords/**
apps/backend/src/novel_signal/modules/visibility/**
apps/backend/src/novel_signal/modules/listings/**
apps/backend/src/novel_signal/modules/commerce/**
apps/backend/src/novel_signal/modules/collection/**
apps/backend/src/novel_signal/collectors/**
apps/backend/src/novel_signal/parsers/**
apps/backend/tests/**/universe/**
apps/backend/tests/**/keywords/**
apps/backend/tests/**/visibility/**
apps/backend/tests/**/listings/**
apps/backend/tests/**/commerce/**
apps/backend/tests/**/collection/**
apps/web/app/universe/**
apps/web/app/keywords/**
apps/web/app/products/**
```

Akanksh also owns Amazon SP-API, Brand Analytics, Google Search Console, and public Amazon.in collection. Palguna agents must not change those adapters.

If Palguna needs a contract change in an owned path, record the request in the PR and let Akanksh make the change. Do not work around it by duplicating business rules.

## 4. Required S1 corrections before integration

Akanksh's current S1 branch must resolve these review findings:

1. Enforce unique `(platform, asin)` identity for competitor products.
2. Implement the documented `record_type` CSV contract using names and ASINs instead of internal UUIDs.
3. Support all records through real pagination; do not stop at the first 50.
4. Ask for confirmation before archiving.

Palguna reviews the corrected migration, CSV behavior, frontend pagination, archive confirmation, and tests. These fixes stay on Akanksh's branch.

## 5. Git and worktree model

### Permanent branches

```text
main                 production-ready history
week1/integration    shared Week 1 integration branch
```

Create `week1/integration` from the latest `main`. Every task branch starts from the latest `week1/integration`.

### One worktree per subagent

Never run parallel subagents in the same checkout. Give each subagent its own branch and Git worktree. Example layout outside the main checkout:

```text
E:\Novel-Signal-worktrees\pal-contracts
E:\Novel-Signal-worktrees\pal-actions-api
E:\Novel-Signal-worktrees\pal-actions-web
E:\Novel-Signal-worktrees\pal-sources
E:\Novel-Signal-worktrees\pal-operations
```

Palguna creates and removes worktrees. Subagents only work inside their assigned worktree.

### Branch rules

- One branch owns one reviewable result.
- Branch names use `pal/<area>-<result>`.
- Never share a branch between agents.
- Never let an agent merge its own pull request.
- Rebase the task branch on the current `week1/integration` before final review.
- Merge approved work into `week1/integration` throughout the week.
- Merge `week1/integration` into `main` only after full acceptance.
- Do not force-push after review starts unless the reviewer agrees.

### Commit rules

- One clear behavior per commit.
- Aim for fewer than 300 changed lines per commit where practical.
- Put a migration in its own commit.
- Put generated files in a separate commit.
- Do not mix cleanup with feature work.
- Tests belong in the same PR as the behavior.
- Use prefixes such as `feat(actions):`, `fix(web):`, `test(ads):`, and `docs(ops):`.

Each PR description must state:

- outcome;
- files owned;
- migrations added;
- contracts consumed or changed;
- tests run;
- manual verification;
- known limits;
- dependency PRs.

## 6. Parallel execution map

Work runs in four batches. Tasks inside a batch can run in parallel when they have separate worktrees and file ownership.

```text
Batch 0: Integration baseline
    -> Batch 1: contracts | actions backend | source adapters | web foundation
    -> Batch 2: actions UI | sources UI | operations backend | product screens
    -> Batch 3: overview | operations UI | deployment | end-to-end release
```

Palguna should keep one agent slot available for review, conflict repair, and coordination.

## 7. Batch 0 - integration baseline

### Task P0: Create the integration branch

**Owner:** Palguna directly  
**Branch:** `week1/integration`  
**Parallel:** No

Actions:

1. Fetch the latest remote branches.
2. Create `week1/integration` from the latest accepted `main`.
3. Confirm Palguna's scaffold is present.
4. Add Akanksh's corrected S1 PR only after its four review findings pass.
5. Run backend and frontend checks.
6. Record the accepted OpenAPI and migration state.

Exit checks:

- clean integration branch;
- corrected S1 merged;
- migrations apply from an empty database;
- backend and frontend checks pass;
- no unresolved ownership overlap.

## 8. Batch 1 - four independent foundations

### Agent P1: Shared backend contracts and access gate

**Branch:** `pal/shared-contracts`  
**Owns:**

```text
apps/backend/src/novel_signal/api/errors.py
apps/backend/src/novel_signal/api/pagination.py
apps/backend/src/novel_signal/api/dependencies.py
apps/backend/src/novel_signal/auth/**
apps/backend/tests/unit/api/**
apps/backend/tests/integration/auth/**
```

Avoid changing `db.py`, `main.py`, or `api/router.py` in this branch. Provide exported helpers that the integration commit can wire later.

Build:

- stable API error envelope;
- cursor request and response helpers;
- internal admin actor dependency;
- mutation audit metadata;
- environment-based access gate suitable for Week 1;
- tests for missing, invalid, and valid access.

Suggested commits:

1. `feat(api): add shared error envelope`
2. `feat(api): add cursor pagination contracts`
3. `feat(auth): add internal admin access gate`
4. `test(auth): cover access and audit behavior`

Exit checks:

- no endpoint leaks secret values;
- unauthorized mutations fail clearly;
- helpers can be adopted without importing module internals.

### Agent P2: S10 actions backend

**Branch:** `pal/actions-backend`  
**Owns:**

```text
apps/backend/src/novel_signal/modules/actions/**
apps/backend/tests/unit/actions/**
apps/backend/tests/integration/actions/**
apps/backend/migrations/versions/*_create_change_action_tables.py
docs/s10-actions/**
```

Build:

- `change_events`, `actions`, and `action_status_history` models;
- unique event fingerprint;
- repository and service boundaries;
- change list and detail API;
- create action from change;
- direct action create/list/detail where required by `SPEC.md`;
- valid transitions between `open`, `in_progress`, `done`, and `dismissed`;
- required outcome note for closed actions;
- status history and audit actor;
- cursor pagination and filters;
- unit, relation, service, and API tests.

The service consumes IDs and published event facts. It must not import Akanksh repositories or parser code.

Suggested commits:

1. `feat(actions): add change and action migration`
2. `feat(actions): add models and repository`
3. `feat(actions): add transition service`
4. `feat(actions): expose change and action APIs`
5. `test(actions): cover fingerprints and transitions`
6. `docs(actions): add contracts and verification`

Exit checks:

- retrying the same change creates one event;
- one change can create an owned action;
- invalid transitions are rejected;
- closed action keeps its outcome and full history.

### Agent P3: Amazon Ads and Meta adapter foundation

**Branch:** `pal/source-adapters`  
**Owns:**

```text
apps/backend/src/novel_signal/sources/amazon/ads_api.py
apps/backend/src/novel_signal/sources/meta/marketing_api.py
apps/backend/src/novel_signal/sources/meta/ad_library.py
apps/backend/src/novel_signal/modules/ads/**
apps/backend/tests/unit/sources/amazon_ads/**
apps/backend/tests/unit/sources/meta/**
apps/backend/tests/integration/ads/**
docs/s4-ads/**
```

Do not edit `sources/base.py`, `sources/registry.py`, collection models, raw storage, or job models. Build against their public interfaces. If an interface is missing, document the exact contract request for Akanksh or the integration owner.

Build:

- credential and connection validation;
- Amazon Ads profile discovery;
- campaign structure and search-term reporting clients;
- Meta campaign, ad set, ad, creative, and insights clients;
- supported Meta Ad Library client kept separate from private Meta data;
- pagination, date windows, rate limits, and bounded retries;
- normalized result types carrying raw response metadata;
- mocks and fixtures that need no live credentials;
- permission errors that never trigger scraping as a fallback.

Suggested commits:

1. `feat(ads): add Amazon Ads client contracts`
2. `feat(ads): add profile and reporting pagination`
3. `feat(meta): add Marketing API client`
4. `feat(meta): add supported Ad Library client`
5. `test(sources): add permission and pagination fixtures`
6. `docs(ads): document source boundaries`

Exit checks:

- raw payload and cursor metadata are available to S12 storage;
- the second sync can resume without duplicate logical rows;
- permission failures are clear;
- no credential or token appears in logs.

### Agent P4: Shared web foundation

**Branch:** `pal/web-foundation`  
**Owns:**

```text
apps/web/app/layout.tsx
apps/web/app/globals.css
apps/web/components/**
apps/web/lib/**
packages/api-client/**
apps/web/tests/shared/**
```

This is the only branch allowed to change `layout.tsx`, `globals.css`, or the shared API client during Batch 1.

Build:

- typed request wrapper and API error handling;
- access-token attachment;
- cursor pagination utilities;
- shared loading, empty, error, unknown, and stale states;
- confirmation dialog;
- table, filter, freshness, evidence, and measured/derived components;
- final navigation shell for all required Week 1 screens;
- shared component tests.

Do not edit any route owned by Akanksh.

Suggested commits:

1. `feat(api-client): add typed request and error handling`
2. `feat(web): add shared data states`
3. `feat(web): add table and pagination components`
4. `feat(web): add confirmation and evidence components`
5. `feat(web): complete Week 1 navigation shell`
6. `test(web): cover shared components`

Exit checks:

- unknown never renders as zero;
- stale data is visible;
- destructive actions require confirmation;
- list screens can paginate beyond 50 records.

## 9. Batch 1 integration checkpoint

Palguna reviews and merges Batch 1 PRs in this order:

1. `pal/shared-contracts`
2. `pal/web-foundation`
3. `pal/actions-backend`
4. `pal/source-adapters`

Palguna then makes one small integration-only branch, `pal/batch1-wiring`, which alone may update shared registries and startup files:

```text
apps/backend/src/novel_signal/main.py
apps/backend/src/novel_signal/api/router.py
apps/backend/src/novel_signal/modules/registry.py
apps/backend/src/novel_signal/sources/registry.py
```

Do not let feature agents edit these shared files. This keeps registry conflicts in one controlled PR.

Checkpoint:

- clean database migration works;
- OpenAPI contains action routes;
- source adapters load with fake configuration;
- the web shell builds;
- Akanksh's merged Universe screen still works.

## 10. Batch 2 - product features

### Agent P5: Changes and Actions frontend

**Branch:** `pal/actions-web`  
**Depends on:** P2 and P4  
**Owns:**

```text
apps/web/app/changes/**
apps/web/app/actions/**
apps/web/tests/changes/**
apps/web/tests/actions/**
```

Build:

- paginated and filterable Changes list;
- Change detail with old value, new value, time, severity, and evidence;
- create-action flow;
- Actions list and detail;
- owner, due date, status, and overdue state;
- transition confirmation;
- outcome note when closing;
- loading, empty, error, stale, and permission states;
- frontend tests.

Suggested commits:

1. `feat(changes): add paginated changes screen`
2. `feat(changes): add evidence-backed detail`
3. `feat(actions): add create and list screens`
4. `feat(actions): add confirmed status transitions`
5. `test(web): cover change-to-action flow`

### Agent P6: Source status and manual sync

**Branch:** `pal/sources-product`  
**Depends on:** P3 and Akanksh's public S12 contracts  
**Owns:**

```text
apps/backend/src/novel_signal/modules/ads/sync_service.py
apps/backend/src/novel_signal/modules/ads/schemas.py
apps/backend/src/novel_signal/modules/ads/repository.py
apps/web/app/sources/**
apps/web/tests/sources/**
apps/backend/tests/integration/ads/test_sync.py
```

Build:

- connection-status API;
- manual sync request and result API;
- Amazon Ads, Meta Marketing, and Ad Library status cards;
- last success, last failure, cursor window, and permission state;
- safe manual-sync confirmation;
- raw-first handoff to S12 storage;
- idempotent normalization after raw storage;
- tests for retry, pagination, duplicates, and permission errors.

Do not create a second raw-capture or job system inside S4.

### Agent P7: Operations backend and Week 1 S11 status

**Branch:** `pal/operations-backend`  
**Depends on:** Akanksh's S12 API and data-quality contracts  
**Owns:**

```text
apps/backend/src/novel_signal/modules/alerts/**
apps/backend/src/novel_signal/operations/**
apps/backend/tests/unit/operations/**
apps/backend/tests/integration/operations/**
docs/operations-api/**
```

Build:

- operations summary service;
- job, failure, quarantine, and data-quality read APIs;
- freshness and capture-success summaries;
- safe retry request with state checks;
- in-app status records for failed, stale, and quarantined states;
- no external notification channels;
- tests proving a failed capture does not replace valid current data.

Consume S12 services or public records. Do not import its repository internals.

### Agent P8: Palguna-owned product integration screens

**Branch:** `pal/product-integration`  
**Depends on:** P4 plus accepted Akanksh APIs  
**Owns:**

```text
apps/web/app/page.tsx
apps/web/app/overview/**
apps/web/app/keyword-detail/**
apps/web/app/product-detail/**
apps/web/tests/overview/**
apps/web/tests/product-integration/**
```

Build only cross-module composition:

- Overview cards for freshness, success, recent changes, open actions, and job health;
- Keyword Detail composition using Akanksh's published S3 API;
- Product Detail composition using Akanksh's S5 and S6 APIs;
- evidence actions, timestamps, stale state, and unknown state;
- simple history table or chart where required.

Do not reproduce rank, listing, price, offer, or availability calculations in TypeScript.

## 11. Batch 2 integration checkpoint

Merge P5-P8 one at a time after rebasing on the latest `week1/integration`. Run after every merge:

- backend lint and type check;
- backend unit and integration tests;
- frontend lint and type check;
- frontend tests and production build;
- migration from an empty database;
- current integration smoke test.

The checkpoint passes when:

- source status is visible;
- a published change appears in Changes;
- it can create and close one action;
- operations show one seeded failure;
- overview reads real APIs rather than static text.

## 12. Batch 3 - operations, deployment, and release

### Agent P9: Operations frontend

**Branch:** `pal/operations-web`  
**Depends on:** P4 and P7  
**Owns:**

```text
apps/web/app/operations/**
apps/web/tests/operations/**
```

Build:

- operations summary;
- paginated job table;
- failure and quarantine views;
- parser version and freshness display;
- data-quality results;
- retry confirmation and result;
- clear disabled/exhausted/running retry states.

### Agent P10: Runtime, CI, and observability

**Branch:** `pal/runtime-release`  
**Owns:**

```text
.github/workflows/**
infra/**
.env.example
docs/runbooks/**
```

Only this agent edits these shared runtime files.

Build:

- API, web, worker, and scheduler service definitions;
- PostgreSQL, Redis, and object-store readiness checks;
- private secret configuration;
- structured logs with request, job, capture, and parser IDs;
- metrics for job success, failure, quarantine, and freshness;
- CI migration test from empty database;
- backend and frontend quality gates;
- local setup, failure, quarantine, retry, and release runbooks.

Do not enable production collection until legal approval, pincode, targets, and credentials are supplied.

### Agent P11: End-to-end acceptance harness

**Branch:** `pal/week1-acceptance`  
**Depends on:** all accepted product APIs  
**Owns:**

```text
apps/backend/tests/e2e/**
apps/web/tests/e2e/**
tests/fixtures/release/**
docs/release-evidence/**
```

Build a fixture-driven acceptance path that proves:

1. Universe and keyword setup load.
2. One search capture and one product capture are represented.
3. Raw evidence metadata is traceable.
4. Valid organic, sponsored, listing, price, and availability facts publish.
5. A supported difference creates exactly one change.
6. The change creates an owned action.
7. The action can be completed with an outcome note.
8. A broken parser fixture is quarantined.
9. The previous valid observation remains current.
10. Operations exposes the failure.

Fixtures must contain no real secrets or unnecessary customer data.

## 13. Integration-owner duties

Palguna does these tasks personally or through one dedicated integration agent. Feature agents must not perform them independently:

- merge order and dependency decisions;
- shared registry wiring;
- shared migration-head resolution;
- OpenAPI contract snapshot review;
- conflict resolution involving Akanksh-owned files;
- full-suite verification;
- release evidence and final PR;
- final call on cross-module contract shape.

When two migration heads exist, create a separate Alembic merge revision. Never edit another owner's already-reviewed migration merely to remove the branch.

## 14. Subagent prompt template

Use this template for each Luna subagent:

```text
Work only on task <TASK ID> from PALGUNA_WEEK1_PARALLEL_IMPLEMENTATION_PLAN.md.

Branch: <BRANCH>
Worktree: <ABSOLUTE WORKTREE PATH>
Owned paths: <PATH LIST>
Read-only dependencies: <PATH LIST>

Do not edit files outside the owned paths. Do not edit Akanksh-owned modules,
collectors, parsers, migrations, or frontend routes. If a required contract is
missing, stop and report the exact contract instead of creating a duplicate.

Make small commits with tests. Before handoff, rebase on week1/integration,
run the task checks, inspect git diff, and provide:
- commits;
- files changed;
- tests run and results;
- contract assumptions;
- blockers or follow-up work.

Do not merge, force-push, or modify another agent's branch.
```

## 15. Review checklist for every PR

### Ownership

- Only assigned paths changed.
- No Akanksh rule was copied into Palguna code.
- No shared registry changed outside an integration PR.
- No unrelated formatting or dependency update exists.

### Data and contracts

- IDs and enums match `SPEC.md`.
- Lists use pagination.
- Unknown remains unknown.
- Measured and derived values are labelled.
- Evidence and timestamps remain traceable.
- Raw data is stored before normalization where required.
- Retry is idempotent.

### Safety

- No secrets in code, fixtures, logs, or screenshots.
- Destructive and retry actions require confirmation.
- Permission failures are explicit.
- No CAPTCHA solving, bypass, or unsupported scraping.

### Quality

- Tests cover success and failure.
- Static checks pass.
- Migration upgrades from empty database.
- API examples are present.
- Manual verification steps are reproducible.

## 16. Final merge order

Recommended order into `week1/integration`:

1. Corrected Akanksh S1.
2. Shared contracts.
3. Shared web foundation.
4. Actions backend.
5. Source adapters.
6. Batch 1 wiring.
7. Remaining accepted Akanksh modules in dependency order: S2, S12, S3, S5, S6.
8. Changes and Actions frontend.
9. Source synchronization product layer.
10. Operations backend.
11. Overview and product integration screens.
12. Operations frontend.
13. Runtime, CI, and observability.
14. End-to-end acceptance harness.
15. Release-only fixes, each as a focused commit.

Do not wait until the last day to merge feature branches into `week1/integration`. Only the merge from `week1/integration` to `main` waits for final acceptance.

## 17. Week 1 final acceptance

Before the final PR to `main`:

- all review comments are resolved;
- worktree and branch list contains no forgotten work;
- database builds from zero and upgrades from the prior accepted state;
- backend lint, type checks, unit tests, integration tests, and E2E tests pass;
- frontend lint, type checks, tests, and production build pass;
- Universe, Keywords, Keyword Detail, Product Detail, Sources, Changes, Actions, and Operations work together;
- all lists paginate;
- all destructive actions confirm;
- raw evidence is linked to every published fact;
- quarantined data never enters current views;
- a supported difference creates one change and one action;
- an action closes only with an outcome note;
- failed jobs and stale data are visible;
- secrets are absent from repository and logs;
- the operator can follow the runbooks without help;
- the approved live smoke test is recorded, or clearly marked blocked if credentials, legal approval, location, or target data are unavailable.

## 18. Definition of Palguna Week 1 complete

Palguna's work is complete when his owned services and screens are tested, Akanksh's accepted modules are integrated without duplicated logic, operations can explain failures, the full fixture flow passes, and `week1/integration` is ready for a small, reviewable final PR into `main`.
