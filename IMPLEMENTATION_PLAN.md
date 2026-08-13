# Novel Signal — Week 1 Implementation Plan

**Duration:** Five build days plus a protected release buffer  
**Team:** Palguna (lead) + Akanksh  
**Outcome:** A live, narrow Amazon.in competitive watchtower covering S1, S2, S3, S5, S6, S12, and the minimum action flow

Week 1 also includes live source connections for Amazon APIs, Google Search Console, Meta APIs, and approved competitor collection. Other marketplaces remain excluded.

## 1. Delivery rule

The team should build vertical slices. Do not complete every database model first and leave the UI or collection path until the end. Each day must finish with a working path that can be shown.

The Week 1 release is complete only when this path works:

```text
setup -> schedule/run -> raw capture -> parse -> validate -> publish
      -> current/history UI -> change event -> assigned action
```

## 2. Team ownership

### Palguna — lead and remaining modules

Owns:

- architecture and repository bootstrap;
- shared database conventions and migration review;
- FastAPI application shell and API contracts;
- Next.js shell and shared UI components;
- action flow and overview;
- authentication/access gate;
- deployment, CI, observability, and runbooks;
- integration review across every module;
- final live acceptance.
- S4 Ad Intelligence;
- S7 Review & Voice-of-Customer;
- S8 Sales & Share Estimation;
- S9 Benchmarking Scorecard;
- S10 Gap & Action Engine;
- S11 Alerting & War Room.

For Week 1, Palguna builds the thin S4 sponsored-observation consumption, the thin S10 action flow, the operations/in-app status part of S11, and all shared product surfaces needed to release. S7, S8, and the full S9 are later-week work.

Palguna also owns Amazon Ads API, Meta Marketing API, and Meta Ad Library integration for S4.

Palguna should not duplicate Akanksh's module code. His main Week 1 job is to keep contracts stable, build the remaining product surfaces, integrate daily, and remove blockers.

### Akanksh — assigned modules

Owns the requested components:

- S1 Universe and Competitor Setup;
- S2 Keyword Intelligence;
- S3 Rank and Visibility Tracking;
- S5 Listing and Content Intelligence;
- S6 Price, Promo and Offer Intelligence;
- S12 Collection Infrastructure.

For Week 1 Akanksh implements the backend domain logic, database migrations, API routes, background jobs, collectors/parsers, validation, and module-level tests for these modules. He also supplies typed API examples and basic module UI components. Palguna integrates them into the final screens.

Akanksh also owns Amazon SP-API, available Brand Analytics reports, Google Search Console, and public Amazon.in competitor collection.

### Joint ownership

- schema review before migrations merge;
- Amazon parser selector review;
- live collection safety review;
- daily end-to-end demo;
- broken-parser and challenge tests;
- release checklist.

### Complete-project module split

| Owner | Modules | Ownership rule |
| --- | --- | --- |
| Akanksh | S1, S2, S3, S5, S6, S12 | Own implementation, tests, module docs, defects, and later-week expansion |
| Palguna | S4, S7, S8, S9, S10, S11 | Own implementation, tests, module docs, defects, and later-week expansion |
| Palguna | Shared frontend, auth, architecture, CI/CD, deployment, observability | Own final integration and release |
| Both | Shared schema contracts and end-to-end acceptance | Review together; Palguna makes the final integration decision |

### Handoff from Akanksh to Palguna

Every completed Akanksh module must provide:

1. Applied Alembic migration and relationship diagram update.
2. Pydantic and OpenAPI contracts with example requests and responses.
3. Service entry points that hide parser and storage internals.
4. Published observation or event contract used by Palguna's modules.
5. Unit, database, parser-fixture, and API tests as relevant.
6. Known failure states and how they appear in Operations.
7. Seed or CSV data needed to demo the module.
8. A short handoff note stating what is complete, what is blocked, and how to verify it.

Palguna reviews each handoff within the same working day. Contract changes are resolved before either person builds more code on top of the old contract.

## 3. Working agreement

- One repository and one shared main development branch policy.
- Short feature branches by vertical slice, not one branch per week.
- Pull requests should remain reviewable and include tests.
- Migrations are reviewed before dependent work starts.
- OpenAPI is the frontend/backend contract.
- No module imports another module's repository directly; use services or shared IDs.
- No observation is written without capture and parser evidence.
- No parser selector is fixed only from one live page; add a golden fixture.
- Daily integration happens before new work starts the next day.
- Do not commit real raw customer/business exports or Amazon pages containing unnecessary data.

## 4. Work packages

### WP0 — Foundation

**Owner:** Palguna  
**Target:** Day 1 morning

Tasks:

1. Create monorepo structure from `SPEC.md`.
2. Configure Python, pnpm, linting, type checks, tests, and pre-commit hooks.
3. Add Docker Compose for PostgreSQL, Redis, and MinIO.
4. Add FastAPI health endpoints and Next.js application shell.
5. Configure SQLAlchemy session management and Alembic.
6. Add structured logging with request/job trace IDs.
7. Add CI skeleton.
8. Add `.env.example` and safe default configuration.

Exit checks:

- one setup command starts dependencies;
- API readiness checks database, Redis, and object store;
- web can call API health;
- empty migration applies in CI.

### WP1 — S1 universe setup

**Owner:** Akanksh  
**Target:** Day 1

Tasks:

1. Implement competitor, product, competitor-product, battle-card, and battle-card-item models.
2. Add validation for ASIN, pack quantity, tracking tier, and comparison basis.
3. Add CRUD services and API routes.
4. Add archive behavior; do not hard-delete referenced masters.
5. Add transactional CSV dry run and import.
6. Add CSV export.
7. Add relationship and uniqueness tests.
8. Supply OpenAPI examples to the frontend.

Palguna integration:

- Build Universe list, forms, battle-card editor, and import result screen.
- Review migration and API naming.

Exit checks:

- a Novel product can be mapped to multiple competitor products;
- duplicate ASINs are rejected clearly;
- invalid CSV imports nothing and returns row errors;
- archived targets cannot be newly scheduled.

### WP2 — S2 keyword and target setup

**Owner:** Akanksh  
**Target:** Day 2 morning

Tasks:

1. Implement keyword normalization and keyword models.
2. Add keyword CSV dry run/import/export.
3. Implement geo, device, and tracking-target models.
4. Seed one desktop profile.
5. Require an approved geo before enabling a live target.
6. Add four-hour keyword and hourly product defaults.
7. Add run-now service with idempotency.
8. Add tests for duplicate normalization and target check constraints.

Palguna integration:

- Build Keywords list, edit form, tracking toggle, cadence display, and run-now action.
- Add application access gate and audit actor dependency.

Exit checks:

- keywords differing only by case/space do not duplicate;
- invalid target combinations fail at API and database levels;
- user can see exactly what will run, where, and when.

### WP3 — S12 collection core

**Owner:** Akanksh  
**Target:** Day 2

Tasks:

1. Implement collection job, raw capture, parser version, parse run, quarantine, and data-quality models.
2. Implement the due-target scheduler with database locking.
3. Implement Celery task routing for search, product, parsing, publishing, and change detection.
4. Implement job state transitions and bounded retries.
5. Implement S3-compatible raw storage and content-addressed keys.
6. Build the Amazon browser context factory.
7. Add challenge and unexpected-page detection.
8. Save raw content before requesting parse.
9. Add failure screenshot capture where useful.
10. Build operations summary, job, and quarantine endpoints.
11. Add source connections, API sync runs, sync cursors, and raw API response records.
12. Add a common source adapter contract with credential, rate-limit, pagination, and raw-first rules.

Palguna integration:

- Configure processes in Compose and shared deployment manifests.
- Build Operations page and status badges.
- Add logs and basic metrics.

Exit checks:

- two scheduler instances cannot create the same slot twice;
- a raw object and row exist before parsing begins;
- challenge fixture never reaches parser publication;
- exhausted retries enter dead-letter state;
- last valid data remains available after a failure.

### WP4 — S3 search, organic rank, and sponsored placement

**Owner:** Akanksh  
**Target:** Day 3 morning

Tasks:

1. Implement Amazon.in search URL builder.
2. Capture page 1 with approved location and desktop profile.
3. Build deterministic search parser v1.
4. Extract placement type, absolute and within-type position, ASIN, title, brand, badges, displayed price, rating, review count, and thumbnail reference where present.
5. Resolve captured ASINs to Novel or competitor records.
6. Implement validation and quarantine rules.
7. Publish `serp_capture` and `serp_results` atomically.
8. Implement latest and history APIs.
9. Derive sponsored first seen, last seen, and daily presence from published captures.
10. Add golden fixtures for organic, sponsored, mixed, empty, and challenge pages.

Palguna integration:

- Build Keyword Detail page with one result table and filters for organic/sponsored.
- Add rank history and evidence panel.
- Ensure Novel and competitor markers are clear.

Exit checks:

- same capture contains Novel and competitor rows;
- sponsored rows can be queried by keyword and competitor product;
- parser failure publishes zero SERP rows;
- a valid scheduled target runs every four hours.

### WP4A — Official API source integrations

**Owners:** Akanksh for Amazon SP-API, Brand Analytics, and Google Search Console; Palguna for Amazon Ads and Meta  
**Target:** Day 3 and Day 4

Akanksh tasks:

1. Implement Login with Amazon token handling and the shared Amazon connection configuration.
2. Implement SP-API clients for the approved Week 1 resources and report jobs.
3. Implement permitted Brand Analytics report requests, polling, download, and normalization.
4. Implement Google Search Console property and search-analytics synchronization.
5. Store every raw API page or report before normalization.
6. Add cursor, date-window, quota, permission, and replay tests.

Palguna tasks:

1. Implement Amazon Ads profiles, campaign structure, search-term reporting, and performance synchronization.
2. Implement Meta Marketing API campaign, creative, and insights synchronization.
3. Implement approved Meta Ad Library access separately from private account data.
4. Add connection-status and manual-sync controls to Operations.
5. Add mocks and fixtures that never require real credentials in CI.

Exit checks:

- each configured source completes one authenticated test call;
- one raw response from every enabled source is stored and traceable;
- a second sync resumes from its cursor or date window without duplicates;
- permission failures are clear and do not trigger scraping as a substitute;
- secrets are absent from logs and database fields.

### WP5 — S5 listing snapshots and diffs

**Owner:** Akanksh  
**Target:** Day 3 afternoon

Tasks:

1. Build Amazon product URL resolution.
2. Build deterministic product parser v1.
3. Extract title, bullets, description, images/hashes, brand, variation data, rating, review count, category, and BSR when visible.
4. Validate expected ASIN and minimum page completeness.
5. Publish listing snapshots.
6. Implement normalized field-level diffing.
7. Generate idempotent listing change events.
8. Add fixtures for normal, unavailable, partial, variation, and changed pages.

Palguna integration:

- Build Product Detail listing tab and before/after change view.
- Add evidence drawer using signed URL metadata.

Exit checks:

- first snapshot creates no false change;
- second changed snapshot creates field-specific events once;
- incomplete page cannot erase existing listing fields;
- ordered image changes are detectable.

### WP6 — S6 price, offer, and availability

**Owner:** Akanksh  
**Target:** Day 4 morning

Tasks:

1. Extend product parser output for price, MRP, coupon, deal text, availability, delivery text, and seller text.
2. Normalize INR into integer paise.
3. Calculate discount only from valid inputs.
4. Calculate price per unit only when product pack data exists.
5. Publish price, offer, and availability observations atomically with the listing snapshot.
6. Implement exact change detectors.
7. Treat unknown availability safely.
8. Add latest/history APIs and tests.

Palguna integration:

- Build Product Detail commerce tab and simple price history chart/table.
- Add current availability and freshness state to Overview.

Exit checks:

- hourly target produces listing, price, offer, and availability observations;
- observed and derived fields are labelled;
- unknown availability cannot generate a false stock-out;
- price and coupon changes link to raw evidence.

### WP7 — Thin action flow

**Owner:** Palguna  
**Target:** Day 4

Tasks:

1. Implement change-event list and filters.
2. Implement action and action-status-history models.
3. Add create-from-change and transition endpoints.
4. Add owner, due date, reason, and evidence requirements.
5. Build Changes and Actions screens.
6. Add overview counts and overdue marker.
7. Add unit, API, and UI tests.

Akanksh support:

- Ensure all detectors use stable event fingerprints.
- Supply useful event summaries and severity defaults.

Exit checks:

- supported changes create one event;
- event creates an assignable action;
- invalid status transitions are rejected;
- closed action retains an outcome note and history.

### WP8 — Data quality, release, and handover

**Owners:** Joint  
**Target:** Day 5

Tasks:

1. Add freshness and capture-success calculations.
2. Add parser field-fill and row-count checks.
3. Seed a deliberate broken golden fixture.
4. Run migration, relation, API, frontend, and end-to-end tests.
5. Run live smoke test against approved small targets.
6. Review browser behavior for challenge safety.
7. Add dashboards/alarms for job failure, quarantine, and stale data.
8. Write local setup, collection failure, quarantine, retry, and release runbooks.
9. Record known limitations and open business inputs.
10. Tag the Week 1 release only after acceptance.

Exit checks:

- broken fixture is quarantined before publication;
- last valid observation remains current;
- all CI gates pass;
- both engineers can operate the system from the runbooks;
- live evidence path is demonstrated and recorded.

## 5. Day-by-day schedule

### Day 1 — Setup and universe

Palguna:

- WP0 foundation.
- Shared schema conventions.
- Universe UI shell.

Akanksh:

- WP1 universe models, services, API, CSV, and tests.
- Start keyword schema.

Joint checkpoint:

- Import products and battle cards from fixture CSV.
- View them in the web application.
- Freeze naming for IDs and target references.

### Day 2 — Keywords and collection backbone

Palguna:

- Keyword UI.
- Auth/access gate.
- Compose and process integration.
- Operations UI shell.

Akanksh:

- Finish WP2.
- Build WP3 scheduler, job states, raw storage, and browser factory.

Joint checkpoint:

- Activate a target.
- Create one idempotent due job.
- Store a raw fixture in object storage.
- Show the job in Operations.

### Day 3 — Search and product evidence

Palguna:

- Keyword Detail UI.
- Product Detail UI shell.
- Evidence panel.

Akanksh:

- Complete WP4 search pipeline.
- Start WP5 product parser and listing publication.
- Connect SP-API/Brand Analytics and Google Search Console source clients.

Joint checkpoint:

- Search fixture travels from job to published rows and UI.
- Live approved manual capture is attempted only if legal/location input is ready.

### Day 4 — Commerce changes and actions

Palguna:

- Complete changes/actions backend and UI.
- Complete overview.
- Connect Amazon Ads API and Meta source clients.

Akanksh:

- Complete WP5 and WP6.
- Complete all supported detectors.

Joint checkpoint:

- Two controlled snapshots generate correct changes.
- A change becomes an assigned, completed action.

### Day 5 — Hardening and release candidate

Palguna:

- CI, deployment, access, observability, and runbooks.
- Acceptance demo script.

Akanksh:

- Golden fixtures, quarantine tests, data-quality metrics, and parser cleanup.
- Fix collection and domain defects from integration.

Joint checkpoint:

- Full acceptance suite.
- Seeded parser break.
- Live scoped smoke test.
- Release candidate deployment.

### Release buffer

Keep at least half a day free after the release candidate for integration defects. Do not fill it with optional features.

## 6. Dependency order

```text
Foundation
  ├─ Universe ──┬─ Product targets ── Product collection ── Listing/commerce observations
  │             └─ Battle cards                         └─ Product changes
  ├─ Keywords ──── Search targets ─── Search collection ── SERP observations
  │                                                        └─ Rank/sponsored changes
  └─ Collection core ── Raw storage ── Parse/validate/publish
                                                    └─ Changes ── Actions
```

The critical path is collection core → raw evidence → parser → validation → publication. If this path slips, pause optional UI polish and protect correctness.

## 7. Pull-request sequence

Recommended small merge order:

1. `foundation/monorepo-runtime`
2. `data/universe-schema-and-api`
3. `data/keywords-targets-and-csv`
4. `collection/jobs-raw-store-and-states`
5. `collection/amazon-search-parser-v1`
6. `feature/serp-publication-and-ui`
7. `collection/amazon-product-parser-v1`
8. `feature/listing-commerce-publication-and-ui`
9. `feature/change-events-and-actions`
10. `ops/quarantine-quality-ci-runbooks`

Do not merge half a parser without fixtures and validation.

## 8. Test and review responsibility

| Area | Author | Reviewer |
| --- | --- | --- |
| Architecture and foundation | Palguna | Akanksh |
| S1/S2 models and API | Akanksh | Palguna |
| S12 scheduler and storage | Akanksh | Palguna |
| Amazon collectors/parsers | Akanksh | Palguna, selector-by-selector |
| Frontend screens | Palguna | Akanksh against API facts |
| Change/action flow | Palguna | Akanksh |
| Safety and quarantine | Joint | Joint demo |
| Deployment and runbooks | Palguna | Akanksh follows runbook fresh |

## 9. Scope protection

If time becomes tight, preserve in this order:

1. Raw evidence before parsing.
2. Validation and quarantine.
3. Required schema and migrations.
4. Search and product observations.
5. Change events and actions.
6. Operations visibility.
7. Basic usable UI.

Do not remove a required Week 1 flow. Reduce only presentation polish, optional filters, charts, and convenience features. Do not add page 2, more locations, more marketplaces, ML, or direct BOS integrations during Week 1.

## 10. Risks and controls

| Risk | Early signal | Control | Owner |
| --- | --- | --- | --- |
| Amazon layout varies | fixture/live fields disagree | versioned parser, fallbacks, quarantine | Akanksh |
| Collector is blocked | challenge rate rises | low concurrency, backoff, stop and report | Akanksh |
| Bad parse looks valid | row/fill metrics shift | validation, canary, golden fixtures | Joint |
| Schema churn blocks parallel work | repeated migration conflicts | Day 1 schema review, additive changes | Palguna |
| Frontend waits for backend | contract unclear | OpenAPI examples and fixture server | Palguna |
| Live inputs arrive late | no approved ASINs/keywords | publish CSV templates Day 1 | Palguna |
| One-week scope is overloaded | critical path slips by Day 3 | stop optional polish, pair on pipeline | Palguna |
| Job retries duplicate facts | repeat events/rows | idempotency keys and fingerprints | Akanksh |
| Unknown values cause false alerts | missing page fields | completeness validation and safe unknown state | Joint |

## 11. Daily lead checklist

At the start of each day:

- pull and apply migrations;
- run the fast test suite;
- review current critical path;
- confirm required business input is available;
- assign one clear outcome to Akanksh.

At the end of each day:

- merge or integrate working slices;
- run the end-to-end fixture path;
- inspect one raw capture and its published facts;
- record blockers and schema decisions;
- update the next day's order.

## 12. Guidance for Akanksh's module work

For every component, require this handoff:

1. Model and migration.
2. Pydantic request/response schema.
3. Repository and service rules.
4. API or task entry point.
5. Unit tests.
6. Database or fixture integration test.
7. Example request and response.
8. Error states and operator note.

For a parser, also require:

1. Parser version.
2. Source golden fixture.
3. Expected normalized JSON.
4. Field-fill metrics.
5. Challenge/invalid fixture.
6. Proof that failure quarantines instead of publishing.

## 13. Release checklist

### Product

- [ ] Universe can be imported and edited.
- [ ] Battle cards map Novel to competitor products.
- [ ] Keywords and tracking targets can be managed.
- [ ] Four-hour search and hourly product schedules work.
- [ ] Organic and sponsored page-1 results are shown.
- [ ] Listing, price, offer, and availability history is shown.
- [ ] Evidence opens for every published fact.
- [ ] Changes can create assigned actions.
- [ ] Operations shows freshness, failures, and quarantine.

### Data and safety

- [ ] Raw capture is stored before parsing.
- [ ] Raw content is immutable and private.
- [ ] Parser version is attached to every observation.
- [ ] Invalid captures publish no observations.
- [ ] Challenge detection stops and reports.
- [ ] No login, CAPTCHA solving, or bypass exists.
- [ ] Measured and derived fields are distinct.
- [ ] Unknown is never displayed as zero.

### Engineering

- [ ] SQLAlchemy models and Alembic migrations are reviewed.
- [ ] ER diagram matches the schema.
- [ ] CI passes all gates.
- [ ] Containers build and start.
- [ ] OpenAPI client is current.
- [ ] Database backup and object-store retention are configured for the shared environment.
- [ ] Logs contain trace IDs and no secrets.
- [ ] Runbooks have been followed by both engineers.

### Acceptance proof

- [ ] Fixture end-to-end test passes.
- [ ] Seeded broken parser is quarantined.
- [ ] Last valid observation survives a later failed capture.
- [ ] Approved live search smoke test is recorded.
- [ ] Approved live product smoke test is recorded.
- [ ] Known limits and open decisions are handed over.

## 14. Definition of Week 1 complete

Week 1 is complete when the client can use the deployed internal product to configure an approved Amazon.in watchlist, view fresh evidence-backed search and product observations, inspect supported changes, assign work, and see when collection or parsing is unhealthy.

It is not complete if only the UI, only the database, or only a collector script works.
