# Novel Signal MVP Implementation Plan

## 1. Product outcome

Deliver a usable Amazon.in competitive-intelligence workflow for Novel:

`Novel SKU -> keyword -> Amazon capture -> evidence -> parsed observation -> competitor proposal -> approval -> battle card -> action`

The MVP must help a category or marketing user answer:

- Where do we rank against competitors?
- What changed?
- How reliable and fresh is the data?
- What action should we take next?

## 1A. Target operating workflow

The primary user action is a CSV upload of Novel Amazon products. The user should not need to manually create competitors or keywords for the normal workflow.

```text
CSV upload
→ validate and import Novel products
→ enrich Novel products from Amazon.in
→ generate and score keywords
→ collect Novel rank and product data
→ daily competitor scan
→ score and deduplicate competitor ASINs
→ activate high-confidence competitors
→ create review proposals for uncertain competitors
→ collect competitor data
→ update battle cards, gaps, alerts, and actions
```

The existing implementation already provides the main foundations: universe CSV import, Amazon product and SERP collection, raw evidence, publication, rank visibility, listings, price monitoring, reviews, scorecards, actions, alerts, and PostgreSQL-backed collection jobs. The next implementation work should connect these foundations into this automatic workflow rather than create parallel systems.

### Product import contract

The minimum supported upload should be:

```csv
internal_sku,marketplace_product_id,product_url
```

The importer may accept optional fields such as `name`, `brand`, `category`, `pack_quantity`, `pack_unit`, and `tracking_tier`. Missing optional fields are enriched from the public Amazon product page or placed in a review queue. Invalid rows must not block valid rows from importing.

## 2. MVP scope

### Included

- Amazon.in public, logged-out search and product-page collection.
- Novel SKU, keyword, competitor, tracked-entity, and battle-card setup.
- Raw evidence storage and inspectable evidence links.
- Versioned parsing, validation, quarantine, and idempotent reprocessing.
- Organic rank, sponsored presence, share of voice, price, price-per-unit, availability, listing fields, rating, review count, BSR, badges, and change history.
- Competitor discovery proposals requiring analyst approval.
- Battle cards, basic scorecards, gaps, actions, and operational health views.
- Demo authentication and workspace isolation.

### Deferred

- Competitor spend, units, revenue, and market-share claims without validated models.
- Google Ads, Meta Ads, additional marketplaces, quick commerce, and D2C integrations.
- CAPTCHA, login-wall, or bot-detection bypass.
- Automatic activation of uncertain competitor matches.
- General-purpose BI and conversational assistant features.

## 3. Deployment constraint

The MVP must run with one Render web service, one PostgreSQL database, and one S3-compatible object store for raw evidence. The web service runs an internal scheduler. It must not require a separate Render Cron service, Redis, Celery, Kubernetes, or a background worker.

Collection work is planned, claimed, and processed in bounded batches directly from PostgreSQL. If a Cron run reaches its time limit, it checkpoints progress and resumes on the next run.

### Runtime rules

- FastAPI handles short API requests; long collection work runs from the Cron command.
- PostgreSQL stores configuration, jobs, attempts, observations, metrics, actions, alerts, and operational state.
- Object storage stores raw HTML, provider responses, and screenshots; large payloads must not be stored in PostgreSQL.
- Job claiming uses PostgreSQL locking or an equivalent safe claim mechanism.
- Jobs have bounded batch size, timeout, attempt limit, retry time, and terminal state.
- Retention and dashboard queries must be bounded with indexes and pre-aggregates.
- Collection concurrency remains conservative and is controlled in application code.

Required deployment configuration includes `DATABASE_URL`, `INTERNAL_AUTH_SECRET`, `CORS_ORIGINS`, object-store settings, collection limits, and optional provider credentials.

Render must run migrations as a release step. The web service starts the internal scheduler during FastAPI lifespan and calls the existing PostgreSQL-backed collection runner in bounded batches. The CLI `collect-due` command remains available for local operations and emergency manual runs.

## 4. API-delay strategy

Amazon API approval is not a release dependency. The product ships first in public-data mode and adds first-party APIs later without replacing the data model.

### Public Amazon mode — available now

- Uses only approved public, logged-out Amazon.in search and product pages.
- Shows competitor rank, observed sponsored placement, title, bullets, images, price, discount, coupon, rating, review count, BSR, badges, availability, and change history.
- Requires no Amazon API key.
- Does not claim Novel private sales, inventory, margin, campaign performance, competitor spend, units, or revenue.

### First-party Amazon mode — enabled after approval

- Adds Amazon SP-API, Amazon Ads API, and Brand Analytics.
- Imports Novel-owned catalog, inventory, orders, listings, pricing, campaign performance, search terms, and approved reports.
- Uses the same evidence, observation, scorecard, and action contracts.
- Must be additive; API activation must not replace the public-data schema or dashboard.

The UI must show the active source mode. API-dependent values must be labelled `not connected` or `unknown`, never zero.

### Phase 0A — Three-day Amazon public-data release

**Goal:** deliver one real, evidence-backed Amazon workflow before API approval.

Build one Novel product, a small keyword set, manual competitor ASIN/URL setup, Amazon search and product capture, raw evidence, parsers, published observations, a battle card, basic change history, and collection-health states.

Do not build automatic discovery, advanced scorecards, market-share estimates, competitor spend, Amazon Ads ingestion, Brand Analytics ingestion, or additional marketplaces for this release.

**Exit criteria:** one real Amazon keyword can be collected, parsed, displayed beside a Novel product and competitor, and traced to raw evidence. Blocked or malformed captures are failed or quarantined.

### Phase 0B — Public-mode completion

Add competitor proposals and approval, scheduled tiers, rank history, Share of Voice, price-per-unit, listing diffs, availability changes, scorecards, gaps, actions, alerts, golden files, and parser canaries.

### Phase 0C — API activation

Add credential verification, secure storage, Novel catalog/seller imports, Amazon Ads and Brand Analytics reports, first-party reconciliation, provider freshness, and private metrics. This must populate existing contracts without schema replacement.

## 5. Delivery phases

### Phase 0 — Product and technical readiness

**Goal:** confirm the first customer workflow and remove delivery blockers.

**Work:**

- Audit current models, migrations, APIs, UI routes, tests, and worktree changes.
- Confirm ownership boundaries for S1, S2, S3, S5, S6, and S12.
- Confirm the Amazon.in legal and collection boundary.
- Select initial 30 Novel SKUs, 200 priority keywords, and 150 tracked products.
- Define freshness, confidence, publication, quarantine, and unknown-value rules.
- Confirm storage, scheduler, browser, and deployment configuration.
- Confirm PostgreSQL-backed job claiming, checkpointing, and single-instance operating limits.

**Exit criteria:** approved seed data, approved collection boundary, one migration head, and a signed-off MVP workflow.

### Phase 1 — Access and universe setup

**Goal:** allow a user to configure what Novel Signal tracks.

**Work:**

- Implement login, logout, session validation, and protected API routes.
- Implement workspace and membership checks on every protected request.
- Add Novel product setup with Amazon ASIN validation and duplicate prevention.
- Add competitors and tracked entities.
- Add keyword management with marketplace, locale, device, geo, priority, and tier.
- Add battle-card mappings with rationale and approval state.
- Add demo data labels and readiness checks.

**Exit criteria:** a new user can configure a valid Novel SKU, keyword set, competitor, and battle card without database edits.

### Phase 2 — Evidence and collection foundation

**Goal:** collect Amazon data safely and preserve trustworthy evidence.

**Work:**

- Implement collection jobs, attempts, retries, terminal states, and idempotency keys.
- Implement allowlisted Amazon.in URL generation.
- Add conservative rate limits, bounded concurrency, timeout, backoff, and jitter.
- Capture raw HTML, response metadata, and permitted screenshots before parsing.
- Stop and record a failure for CAPTCHA, login, bot challenge, robots restriction, or blocked access.
- Add Resync API and collection job progress endpoint.
- Add collection health, freshness, completeness, and failure reporting.
- Add bounded Cron batches, checkpointing, and PostgreSQL-backed resume behavior.
- Add retention and aggregate refresh jobs that fit within the single-instance limit.

**Exit criteria:** a configured keyword or product can be collected, inspected, retried, and reported as success, partial, failed, or challenged.

### Phase 3 — Parsing and publication

**Goal:** convert raw captures into safe, evidence-linked observations.

**Work:**

- Add versioned parsers for search results and product pages.
- Parse identity, rank, sponsored state, title, bullets, images, price, discount, coupon, rating, review count, BSR, badges, and availability.
- Validate IDs, timestamps, currencies, ranges, and required fields.
- Quarantine malformed, incomplete, duplicate, or suspicious output.
- Add parser versions, golden files, field-fill checks, and statistical canaries.
- Publish immutable observations only after validation.
- Emit deterministic change events after publication.
- Add evidence detail endpoints and evidence drawer UI.

**Exit criteria:** repeated processing creates no duplicate published observations, and a seeded parser break is quarantined before dashboard publication.

### Phase 4 — First intelligence and competitor discovery

**Goal:** create the first useful competitive view.

**Work:**

- Calculate organic rank, sponsored presence, top-3/top-10 presence, and share of voice.
- Calculate price-per-unit using configured pack-size information.
- Track listing, price, offer, availability, rating, review-count, BSR, and badge changes.
- Discover competitor candidates from repeated keyword and related-product appearances.
- Score candidates using recurrence, rank strength, category match, and SKU overlap.
- Add approve, reject, archive, and manual-correction workflows.
- Keep unapproved candidates out of active scorecards and alerts.

**Exit criteria:** a repeated competitor appears in a review queue with evidence, and approval creates an active competitor and battle-card relationship.

### Phase 5 — Dashboard, scorecard, gaps, and actions

**Goal:** turn observations into decisions.

**Work:**

- Build overview dashboard with freshness and data-quality status.
- Build keyword rank and visibility view.
- Build SKU battle-card view.
- Build listing, pricing, availability, and change-history views.
- Build competitor discovery queue.
- Build a measured-only initial scorecard across visibility, price, content, reviews, and availability.
- Generate explainable gaps only from fresh published observations.
- Create actions with owner, due date, priority, SLA, evidence, and status.
- Add loading, empty, stale, partial, quarantined, error, estimated, and unknown states.

**Exit criteria:** a user can identify a lagging area, inspect its evidence, create an assigned action, and later record its outcome.

### Phase 6 — Hardening and release

**Goal:** prove the MVP is safe to operate.

**Work:**

- Run Ruff, mypy, pytest, frontend typecheck, frontend tests, and frontend build.
- Test PostgreSQL migrations and confirm one Alembic head.
- Test the production-like flow using only the Render web service, PostgreSQL, object storage, and Cron.
- Verify interrupted jobs resume without duplicate observations.
- Verify concurrent claims cannot process the same job or entity window twice.
- Test workspace isolation and credential/data access boundaries.
- Test success, empty, malformed, timeout, rate-limit, blocked, stale, quarantined, and duplicate flows.
- Run a controlled Amazon canary with approved URLs and conservative limits.
- Document environment variables, deployment, scheduler, storage, legal boundary, and known limitations.
- Review dashboard claims to ensure demo and unknown values are labelled correctly.

**Release gate:** all MVP acceptance criteria pass, the Amazon canary succeeds, and no live capability is claimed without source-backed verification.

## 4. Core acceptance criteria

1. A user can sign in and configure a Novel SKU, keyword, competitor, and battle card.
2. A configured keyword produces an Amazon.in capture with raw evidence.
3. A product capture publishes inspectable fields with timestamps, confidence, parser version, and evidence reference.
4. The system reports organic rank and sponsored presence from the same capture.
5. Price, price-per-unit, availability, listing, rating, review count, BSR, and badge changes are visible as history.
6. A repeated competitor is proposed with evidence and remains inactive until approved.
7. Reprocessing evidence is idempotent.
8. Challenges and malformed data become failures or quarantined records, never zeroes or published facts.
9. Every dashboard shows freshness and data-quality status.
10. Every gap and action links to inspectable evidence.
11. The backend runs with one Render web service and one PostgreSQL database.
12. Collection runs through Render Cron without Redis, Celery, or a separate worker.
13. Interrupted collection resumes from a checkpoint without duplicate work.
14. Raw evidence is stored in object storage and referenced from PostgreSQL.

## 5. Delivery controls

- Work in thin vertical slices: setup, collect, publish, compare, act.
- Reuse existing models, contracts, and migrations before creating new ones.
- Do not add new platforms until the Amazon slice meets reliability targets.
- Keep routers thin and business rules in services.
- Never rewrite historical observations.
- Preserve unrelated worktree changes.
- Report measured, estimated, and unknown values separately.
- Keep API requests short; run collection and retention in bounded Cron batches.
- Treat PostgreSQL as the MVP queue and operational source of truth.
- Monitor database size, query latency, Cron duration, object-storage usage, and throughput.

## 6. Initial KPIs

- Capture success rate: target at least 98% for two consecutive weeks.
- T1 freshness: target within 60 minutes.
- Competitor price-change detection: target within two hours.
- New competitor-SKU detection: target within 24 hours.
- Published observations with evidence: target 100%.
- Quarantined records reaching metrics: target 0.
- Duplicate observations from reprocessing: target 0.
- Actions with owners and due dates: target 100%.
- Cron completion within its runtime limit: target at least 99% of scheduled runs.
- Duplicate job claims after restart or retry: target 0.

## 7. Immediate next actions

1. Complete the repository and implementation audit.
2. Obtain the initial Novel SKU, competitor, keyword, geo, and legal inputs.
3. Confirm the Amazon public-collection canary scope.
4. Close Phase 1 access and universe setup gaps.
5. Run one end-to-end vertical slice before expanding module scope.
6. Confirm Render service, Cron, PostgreSQL, and object-store configuration in staging.
