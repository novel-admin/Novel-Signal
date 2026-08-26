# Novel Signal Amazon, Google, and Meta MVP Implementation Plan

## 1. Purpose

Build the smallest reliable version of Novel Signal that turns Amazon, Google,
and Meta evidence into clear decisions for Novel's commercial team.

The MVP must answer:

1. What are competitors doing?
2. Where is Novel leading or lagging?
3. What changed?
4. How fresh and reliable is the evidence?
5. What should the team do next?

The product is an internal Novel Group platform. It is not a general analytics
tool and is not a conversational AI product.

## 2. Fixed product scope

### 2.1 Included sources

| Source | Data owned by Novel Signal |
| --- | --- |
| Amazon SP-API | Novel catalogue, listings, inventory, pricing, offers, and permitted seller data |
| Amazon Ads API | Novel campaigns, targets, search terms, spend, clicks, orders, sales, ACOS, and ROAS |
| Amazon Brand Analytics | Search Query Performance, Top Search Terms, and permitted keyword evidence |
| Amazon.in public pages | Approved logged-out SERPs and product pages for rank, sponsored placement, price, offers, stock, badges, ratings, BSR, and listing content |
| Google Search Console | Novel queries, pages, impressions, clicks, CTR, position, country, and device |
| Google Ads API | Novel campaigns, search terms, spend, conversions, conversion value, and ROAS |
| Google public SERPs | Approved keyword results for Novel and competitor organic visibility |
| Google Ads Transparency Center | Public competitor creative and published run information when officially available |
| Meta Marketing API | Novel campaigns, ads, creative, spend, reach, clicks, conversions, and ROAS |
| Meta Ad Library | Public competitor creative, copy, platform, active state, and published run information |

### 2.2 Included modules

- S1 Universe and Competitor Setup
- S2 Keyword Intelligence
- S3 Rank and Visibility Tracking
- S4 Ad Intelligence
- S5 Listing and Content Intelligence
- S6 Price, Promo, Offer, and Availability Intelligence
- S9 Benchmarking Scorecards
- S10 Gaps and Actions
- S11 Alerts
- S12 Collection Infrastructure

S7 review-topic intelligence and S8 competitor sales or market-share estimation
remain outside this MVP. Existing safe foundations may remain in the repository,
but they are not part of the main navigation or MVP completion claim.

### 2.3 Explicitly excluded

- Conversational assistant or chat interface
- Automated bidding, campaign mutation, or listing mutation
- Competitor spend, sales, revenue, bid, conversion, or ACOS estimates
- Flipkart, Meesho, quick-commerce, Shopify, and general social monitoring
- Review NLP and market-share modelling
- Full event war room
- WhatsApp delivery until the shared BOS delivery path is approved
- Proxy or browser behavior intended to evade challenges
- Redis, Celery, MinIO, Kafka, Elasticsearch, Kubernetes, or a data warehouse
- A second frontend framework or client-side state library

## 3. Product principles

### 3.1 Evidence first

Every published observation follows:

`source -> raw evidence -> versioned parser -> validation -> publication -> metric`

Every important value must carry:

- source type
- observed and collected timestamps
- raw evidence reference
- parser version
- publication status
- measured, derived, estimated, or unknown label
- confidence label
- freshness state
- geo and device where relevant
- quarantine reason when rejected

Missing, stale, unpublished, or quarantined data remains unknown. It never
silently becomes zero.

### 3.2 Low user effort

Users should configure the product once and work from a prioritized feed.

- Credentials are configured once in Render environment settings.
- A readiness screen verifies each connection without exposing secrets.
- Scheduled imports and collection run automatically.
- The system proposes universe additions and battle-card mappings from evidence;
  a user only accepts or rejects them.
- Default tracking tiers and alert thresholds come from versioned configuration.
- Filters persist in the URL.
- Empty states explain the next required action.
- Every AI draft can be accepted, edited, or rejected in place.
- Normal workflows never require database edits or manual API requests.

### 3.3 AI is advisory only

AI has exactly two responsibilities:

1. Explain a deterministic, evidence-backed signal in plain language.
2. Draft a recommended action from an approved playbook.

AI must not:

- create facts or estimates
- decide whether evidence is valid
- calculate scores, thresholds, gaps, or alert severity
- publish observations
- change campaigns, bids, listings, prices, or inventory
- assign an owner or close an action without user confirmation
- answer open-ended chat questions

The product remains fully usable when the AI provider is unavailable. In that
case it shows deterministic explanations and playbook actions.

## 4. Production architecture

```text
Vercel
  Next.js web application
        |
        | HTTPS JSON API
        v
Render
  FastAPI web service -----------------------------+
        |                                           |
        |                                           |
  Hourly cron: collect-due                          |
        |                                           |
        +--> Amazon / Google / Meta APIs             |
        +--> approved public collectors              |
        +--> parse / validate / publish              |
        +--> metrics / gaps / alerts / AI drafts     |
                                                    |
Supabase                                           |
  PostgreSQL <--------------------------------------+
  private Storage bucket <--------------------------+
```

### 4.1 Vercel

- Deploy `apps/web` as the Next.js application.
- Use the Render API as the only application data source.
- Store only the public API base URL in browser-visible configuration.
- Do not connect the browser directly to PostgreSQL or expose service-role keys.
- Use Vercel preview deployments against a non-production API environment.

### 4.2 Render web service

- Run FastAPI and the existing routers.
- Handle dashboard authentication, reads, writes, evidence links, source status,
  and manual job requests.
- Never perform long collection or model calls inside an HTTP request.
- Expose liveness and readiness endpoints.
- Apply strict CORS for the approved Vercel domains.

### 4.3 Render scheduled job

Add a single hourly command:

```bash
python -m novel_signal.cli collect-due --max-jobs "$COLLECTION_BATCH_SIZE"
```

The command must:

1. Create due jobs from configured tracking tiers.
2. Claim a bounded batch using PostgreSQL row locking.
3. Execute API or public-page collection.
4. Store immutable raw evidence before parsing.
5. Validate parser output and quarantine failures.
6. Publish idempotent observations.
7. Recalculate only affected metrics.
8. Generate deterministic gaps and alerts.
9. Request AI explanations for eligible new signals.
10. Record a terminal state for every attempt.
11. Exit with a non-zero code when the run itself is unhealthy.

T1, T2, and T3 frequency remains data-driven. The hourly process runs whatever
is due rather than requiring a separate service for every schedule.

### 4.4 Supabase PostgreSQL

- Keep SQLAlchemy and Alembic.
- Use the Supabase session pooler for persistent Render application traffic when
  a direct connection is unavailable.
- Use a direct connection for migrations when supported.
- Configure bounded SQLAlchemy pools and `pool_pre_ping`.
- Set statement and lock timeouts for collection claims.
- Keep one Alembic head.
- Add indexes for scheduled jobs, current observations, dashboard filters,
  fingerprints, and time-range queries.
- Partition only tables that are proven to need it by measured volume; do not
  introduce a second database.

### 4.5 Supabase Storage

- Create one private bucket named `novel-signal-raw`.
- Reuse the existing S3 storage adapter with the Supabase S3 endpoint.
- Store compressed, SHA-256-addressed objects.
- Never overwrite an existing content hash.
- Issue short-lived evidence URLs through the backend.
- Store bucket, object key, digest, size, content type, and timestamps in
  PostgreSQL.
- Apply the document's 90-day raw-evidence retention policy through an explicit,
  tested cleanup command.

### 4.6 Removed production dependencies

- Replace Celery dispatch and retries with the database collection lifecycle and
  the bounded `collect-due` command.
- Remove Redis from required settings and deployment documentation.
- Replace MinIO configuration with Supabase Storage configuration.
- Keep local fakes for unit tests; local Docker services are optional developer
  conveniences, not production requirements.

## 5. Backend design

### 5.1 Layering

Keep the existing module pattern:

- routers: HTTP validation and error mapping
- services: business rules and orchestration
- repositories: SQLAlchemy queries and persistence
- schemas: typed request and response contracts
- source clients: raw external responses only
- parsers: versioned normalization
- collectors: approved public collection
- tasks/CLI: bounded orchestration

Do not create duplicate platform models. Cross-source metrics consume published
observation contracts instead of writing into another module's tables.

### 5.2 Configuration

Add or finalize server-only settings for:

- Supabase database URL
- Supabase direct migration URL
- Supabase S3 endpoint, region, bucket, access key, and secret
- Vercel production and preview origins
- Amazon SP-API credentials and marketplace
- Amazon Ads credentials and profiles
- Google Search Console service credentials and sites
- Google Ads developer token, customer, login customer, and OAuth credentials
- Meta app, token, ad accounts, and Ad Library token
- public collection concurrency, delay, timeout, and geo settings
- collection batch size and maximum attempts
- AI enabled flag, provider, model, timeout, and daily request cap
- evidence signing TTL

Settings validation must fail readiness, not crash import-time application
startup, when an optional source is not configured.

### 5.3 Source connection lifecycle

Each source must implement:

- `configuration_status()`
- `verify_connection()`
- `fetch(request)` returning raw pages
- typed permission, rate-limit, timeout, malformed, and empty-response errors
- cursor or report-job continuation where required
- explicit HTTP timeout
- safe client shutdown

The readiness API returns `configured`, `verified`, `failed`, or `stale`, plus a
sanitized reason and last verification time.

### 5.4 Amazon vertical slice

#### SP-API

- Verify marketplace participation.
- Fetch permitted catalogue, pricing, offers, inventory, and owned-listing data.
- Persist raw responses first.
- Publish owned-product observations with exact source lineage.
- Handle LWA, SigV4, permissions, throttling, pagination, and empty data.

#### Amazon Ads

- Verify configured profiles.
- Request and poll reports with bounded attempts.
- Ingest campaigns, advertised products, targets, search terms, and performance.
- Normalize report rows idempotently.
- Keep attribution window and currency explicit.
- Never compare rows with incompatible attribution windows without a warning.

#### Brand Analytics

- Ingest permitted reports.
- Publish keyword and query-performance evidence.
- Preserve report period and scope.
- Keep unavailable search volume unknown.

#### Public Amazon.in

- Collect approved SERP and product pages only.
- Enforce configured domain, keyword, ASIN, geo, and device boundaries.
- Detect CAPTCHA, consent walls, login walls, and bot challenges.
- Stop and record a challenge failure; never solve it.
- Publish rank, sponsored placement, price, offer, availability, badge, rating,
  review count, BSR, and listing-content observations.

### 5.5 Google vertical slice

#### Search Console

- Verify site access.
- Ingest query and page performance by date, country, and device.
- Publish clicks, impressions, CTR, and average position as measured first-party
  values.
- Use the existing keyword publication path.

#### Google Ads

- Add a raw-first Google Ads source client.
- Verify customer access without logging tokens.
- Ingest campaigns, ad groups, ads, keywords, search terms, spend, conversions,
  conversion value, and status.
- Preserve account timezone, currency, attribution window, and conversion action.
- Handle partial failures and manager-account permissions.

#### Public Google SERP

- Use the existing approved collector and parser.
- Publish Novel and configured competitor domain positions.
- Record geo, device, locale, result type, title, and URL.
- Treat observed ads as sampled presence, not complete campaign coverage.

#### Google Ads Transparency Center

- First validate the supported official access method and permitted fields.
- Implement only an approved, stable access path.
- Store raw evidence and publish advertiser, creative, format, region, dates, and
  destination when provided.
- If no supported automated access is available, mark this source unavailable;
  do not replace it with unapproved scraping.

### 5.6 Meta vertical slice

#### Marketing API

- Verify ad-account access.
- Ingest Novel campaigns, ad sets, ads, creative, spend, reach, impressions,
  clicks, conversions, conversion value, and status.
- Preserve attribution window, currency, timezone, and action type.
- Handle pagination, expired tokens, rate limits, permission denial, and partial
  result sets.

#### Ad Library

- Verify supported access.
- Fetch only approved public competitor ads.
- Publish advertiser, platform, copy, creative reference, start date, stop date
  when supplied, active state, and destination when supplied.
- Never infer spend or performance from missing library fields.

### 5.7 Collection lifecycle

Use the existing collection tables and strengthen them rather than replacing
them.

- deterministic job fingerprint
- due time and tracking tier
- source and target identity
- claim token, claimed time, and worker identity
- attempt number and maximum attempts
- structured failure type and sanitized reason
- retry time with exponential backoff and jitter
- terminal succeeded, failed, dead, or quarantined state
- raw evidence reference
- parser version and parse-run reference
- published observation count
- processing duration and bytes captured

Claims must use a transaction and `FOR UPDATE SKIP LOCKED` or an equivalent
PostgreSQL-safe pattern. A stale claim can be recovered only after its lease
expires. Completion must be fenced by the claim token.

### 5.8 Parsing, validation, and canaries

- Register a semantic parser version per platform and page/report type.
- Store sanitized golden files for each parser.
- Validate required fields, types, ranges, and target identity.
- Quarantine malformed, suspicious, or incomplete output.
- Calculate fill rate, row count, and selected value distributions.
- Compare new runs to the trailing seven-day baseline when enough history exists.
- Quarantine material anomalies before publication.
- Add a seeded layout-break fixture proving the canary blocks bad data.
- Permit reprocessing retained raw evidence with a newer parser version.
- Guarantee that reprocessing does not duplicate observations or events.

### 5.9 Metrics

All metric formulas must be deterministic and versioned.

#### Visibility

- organic rank
- sponsored rank
- rank direction and velocity
- Share of Voice using a documented weighting formula
- new entrant and badge events

#### Advertising

- Novel spend, impressions, clicks, conversions, sales, CPC, CTR, conversion
  rate, ACOS, and ROAS where source fields support them
- competitor sponsored presence from observed Amazon SERPs
- ad-presence days using successful capture IDs as the denominator
- keyword ad breadth
- observed daypart profile
- competitor Meta and Google creative run evidence

#### Listing and commerce

- immutable listing diffs
- content completeness score with versioned rules
- price and price-per-unit comparison
- promotion and offer changes
- availability windows and stock-out events

### 5.10 Scorecards, gaps, actions, and alerts

Scorecard dimensions remain those required by `Novel_signal.md`:

- visibility
- paid presence
- price
- content
- social proof
- availability
- conversion

For the MVP:

- social proof uses measured rating and review-count evidence, not review NLP
- conversion uses Novel first-party evidence only
- unknown inputs produce an unknown cell
- every formula has a version
- every cell stores freshness, confidence, and evidence
- lagging and critical cells create deterministic, idempotent gaps
- a gap creates a draft action from an approved playbook
- users confirm owner and due date before an action becomes active
- impact snapshots are captured at 7, 14, and 30 days
- critical deterministic events create alerts
- alerts support open, acknowledged, and resolved states

Initial alert rules are limited to requirements with measurable inputs:

- competitor appears sponsored on a configured Novel brand keyword
- Novel rank drops beyond its configured threshold
- Novel loses a badge or observed Buy Box state
- competitor price drops beyond its configured threshold
- configured competitor becomes unavailable
- Novel rating crosses its threshold
- new approved competitor creative appears
- source freshness or completeness breaches its threshold
- parser canary quarantines a run

### 5.11 AI explanation and action drafting

Add a small provider interface, not an AI subsystem.

#### Inputs

- deterministic signal type and severity
- metric values and formula version
- exact evidence identifiers and supported evidence excerpts
- entity, keyword, platform, and time window
- approved playbook entries
- freshness and confidence state

#### Structured output

- one-sentence explanation
- why it matters
- evidence citations by supplied identifier
- draft action title
- draft action steps
- expected metric to watch
- uncertainty note

#### Enforcement

- require JSON-schema-valid output
- reject citations not supplied in the input
- reject unsupported numerical claims
- store provider, model, prompt version, input fingerprint, output, and status
- cache by input fingerprint
- cap retries and daily requests
- never send credentials, raw private payloads, reviewer identity, or signed URLs
- mark every output as `AI draft`
- require user acceptance before it affects an active action
- fall back to the deterministic playbook when unavailable or rejected

### 5.12 API surface

Keep APIs additive and cursor-paginated.

#### Setup and sources

- `GET /api/v1/readiness`
- `GET /api/v1/sources`
- `POST /api/v1/sources/{source}/verify`
- `POST /api/v1/sources/{source}/sync-request`

#### Universe

- competitors, products, tracked entities, battle cards, and mapping proposals
- accept or reject mapping proposals with evidence

#### Keywords and visibility

- keyword list and import
- keyword detail with cross-channel time series
- Amazon and Google capture history
- rank, Share of Voice, and ad-presence summaries

#### Ads and creatives

- first-party performance by platform
- search-term performance
- competitor presence and creative library
- creative detail and history

#### Listings and commerce

- snapshots, diffs, prices, offers, and availability events

#### Decisions

- scorecards, gaps, actions, impact, alerts, and AI drafts
- accept, edit, or reject an AI action draft

#### Operations and evidence

- collection jobs, attempts, failures, quarantine, parser versions, data-quality
  checks, and signed evidence access

Every list endpoint must have deterministic ordering, bounded limits, filters,
and typed response schemas with `from_attributes` where ORM objects are returned.

## 6. Frontend design

### 6.1 UI foundation

Replace the growing custom component CSS with a controlled shadcn foundation.

- Keep Next.js App Router, React, and TypeScript.
- Add Tailwind using the shadcn-supported setup.
- Add shadcn components individually; do not install a separate UI framework.
- Use shadcn Chart components backed by Recharts.
- Use Lucide icons.
- Use a restrained neutral palette with one Novel accent color.
- Support light and dark themes only if it does not delay the core workflows;
  dark remains the initial default.
- Use consistent spacing, typography, borders, status colors, and chart tokens.

Initial shadcn components:

- App Sidebar and Sheet
- Breadcrumb
- Button
- Card
- Badge
- Tabs
- Table
- Input, Select, Checkbox, and Date Picker
- Dialog, Alert Dialog, Drawer, and Sheet
- Dropdown Menu
- Tooltip and Popover
- Command
- Skeleton
- Alert
- Progress
- Separator
- Scroll Area
- Chart
- Toast or Sonner

Do not wrap shadcn components without a repeated product-level need.

### 6.2 Information architecture

Reduce the current long module navigation to user workflows:

1. Overview
2. Keywords
3. Products
4. Advertising
5. Changes
6. Scorecards
7. Actions
8. Alerts
9. Operations
10. Settings

Module details can appear as tabs inside these workflows. Reviews and market
share are hidden from MVP navigation.

### 6.3 Shared screen behavior

Every data screen must provide:

- page title and one-line purpose
- freshness and data-quality banner
- URL-backed platform, time, category, brand, keyword, and status filters
- loading skeleton
- useful empty state
- partial-data state
- stale state
- quarantine warning
- retryable error state
- accessible table and keyboard behavior
- evidence drawer close to important values
- CSV export only for the filtered published data shown to users

### 6.4 Overview

Purpose: answer what needs attention today.

Components:

- data-quality banner
- KPI cards for critical alerts, open gaps, overdue actions, and capture health
- Share of Voice trend line by platform
- Novel versus competitors scorecard heatmap
- top changes timeline
- prioritized gaps table
- advertising performance summary by Amazon, Google, and Meta
- action completion and impact summary

Visualizations:

- line chart: Share of Voice trend
- heatmap: SKU by scorecard dimension
- stacked bar: paid versus organic visibility by platform
- compact spark lines inside KPI cards

Never use a chart when a single value or short table is clearer.

### 6.5 Keywords

#### Keyword list

- keyword, category, intent, tier, source, freshness, Amazon rank, Google rank,
  Amazon paid presence, and last movement
- bulk tier and tracking-status actions
- CSV validation and import using existing workflows

#### Keyword detail

- Amazon organic and sponsored positions from the same captures
- Google organic position
- Amazon Ads search-term performance
- Google Ads and Search Console performance
- competitors present by platform
- evidence timeline

Visualizations:

- multi-line rank history with an inverted rank axis
- Share of Voice trend
- hour-by-day Amazon sponsored-presence heatmap
- first-party impressions, clicks, and conversions trend

### 6.6 Products and battle cards

#### Product list

- Novel ASIN, mapped competitor count, tracking tier, current score, freshness,
  price position, availability, and open gaps

#### Battle card

- Novel product and approved competitor products side by side
- price and price-per-unit
- rating and review count
- BSR and badges
- organic and sponsored visibility
- content completeness
- availability
- recent changes
- evidence drawer for every comparison

Visualizations:

- scorecard radar is excluded because it makes exact comparison difficult
- use grouped horizontal bars for dimension scores
- use lines for price, rating, BSR, and rank history
- use an event timeline for listing and availability changes

### 6.7 Advertising

Tabs:

- Performance
- Search terms
- Competitor presence
- Creative library

Performance keeps Amazon, Google, and Meta attribution clearly separated.

Visualizations:

- spend and attributed value trend by platform
- ACOS for Amazon and ROAS by platform
- impressions-to-conversion funnel where source definitions are compatible
- Amazon competitor ad-presence heatmap
- creative activity timeline for Meta and Google

The UI must display currency, timezone, attribution window, and source beside
performance summaries.

### 6.8 Changes

- unified chronological feed for rank, price, offer, availability, badge,
  listing, and competitor creative events
- filters by event, platform, product, competitor, importance, and date
- before-and-after drawer
- raw evidence access
- convert eligible change into an action

Visualizations:

- event-volume trend by event type
- price and rank context chart inside change details

### 6.9 Scorecards

- views by Novel SKU, keyword, competitor, category, and platform where evidence
  supports the level
- seven required dimensions
- leading, competitive, lagging, critical, and unknown states
- trend, confidence, freshness, formula version, and evidence

Visualizations:

- heatmap as the primary view
- dimension trend line in cell detail
- distribution bars by score band

Every lagging or critical cell links to its gap. Unknown cells explain which
evidence is missing.

### 6.10 Actions and AI drafts

- prioritized action queue
- owner, due date, source gap, expected metric, state, and age
- filters for owner, platform, status, severity, and overdue
- action detail with evidence, deterministic reason, AI explanation, draft
  steps, edit history, and impact snapshots
- accept, edit, reject, start, complete, and dismiss controls

AI treatment:

- label as `AI draft`
- show cited evidence immediately below the explanation
- show an uncertainty note
- require explicit acceptance
- show deterministic fallback when AI is unavailable

Visualizations:

- action completion trend
- 7/14/30-day before-and-after metric chart
- overdue and status distribution

### 6.11 Alerts

- open, acknowledged, and resolved queues
- severity, platform, target, observed time, freshness, evidence, linked gap,
  linked action, owner, and SLA state
- acknowledge and resolve controls
- daily-cap and digest configuration only after BOS delivery is integrated

Visualizations:

- alert volume by severity
- acknowledgement-time trend
- source-health context for data-quality alerts

### 6.12 Operations and settings

#### Operations

- capture success and completeness
- freshness by source and tier
- scheduled, running, failed, dead, and quarantined jobs
- failure categories
- parser versions and canary results
- storage and retention status
- manual retry for safe retryable jobs

Visualizations:

- capture success trend against the 98% target
- freshness SLA trend
- failures by source and category
- parser fill-rate trend

#### Settings

- sanitized source readiness
- verify connection buttons
- tracking schedules and thresholds
- category, geo, and device configuration
- AI enabled state and usage cap
- no secret values returned to the browser

### 6.13 Frontend data architecture

- Keep a small typed API client under the existing app structure.
- Generate or manually maintain types from backend response schemas in the
  existing API-client package.
- Prefer React Server Components for initial reads when authentication permits.
- Use client components only for filters, charts, forms, dialogs, and live
  interactions.
- Do not add Redux, Zustand, or React Query for the MVP.
- Implement a shared fetch wrapper with credentials, timeout, error mapping, and
  request ID handling.
- Preserve filters in URL search parameters.
- Use accessible chart summaries and table alternatives.

## 7. Database and migration plan

### 7.1 Audit first

Before adding migrations:

1. Import every existing model in Alembic metadata.
2. Produce the current revision graph.
3. Confirm one head.
4. Compare existing tables with this plan.
5. Reuse existing tables and additive columns.
6. Identify SQLite-only assumptions.

### 7.2 Expected additive storage

Add only when absent:

- source verification state and sanitized error
- Google Ads raw-sync and normalized first-party records
- Google transparency creative records when a supported integration exists
- AI explanation run and draft records
- AI prompt/model version and input fingerprint
- mapping proposal evidence and review state
- metric formula version and unknown reason
- alert SLA timestamps
- collection lease token and lease expiry where not already present
- retention-run records

### 7.3 Constraints

- unique source/report/page fingerprint
- unique published observation fingerprint
- unique change-event fingerprint
- unique gap and alert fingerprint
- valid state checks
- evidence foreign keys
- no active action without owner and due date
- no AI draft without source signal and evidence bundle
- deterministic ordering indexes for cursor pagination

### 7.4 PostgreSQL verification

- apply all migrations to a clean Supabase-compatible PostgreSQL database
- upgrade an existing database snapshot
- downgrade reversible migrations where safe
- verify one Alembic head
- run integration tests against PostgreSQL
- inspect query plans for dashboard time-range queries
- confirm connection behavior through the selected Supabase endpoint

## 8. Security and privacy

- Keep all source, database, storage, and AI secrets on Render.
- Redact credentials and authorization headers from logs and errors.
- Never return raw private API payloads directly to the frontend.
- Use short-lived signed evidence URLs.
- Keep public reviewer identity out of product responses; hash when needed.
- Apply configured domain and target allowlists to public collectors.
- Enforce dashboard authentication on every non-public API route.
- Use secure, HTTP-only, same-site cookies.
- Apply CSRF protection to state-changing browser requests.
- Restrict CORS to production and approved preview origins.
- Record user-visible action and alert transitions in an audit trail.
- Apply request body limits and bounded pagination.
- Perform dependency and secret scanning in CI.
- Complete legal approval before production public-page collection.

The MVP retains the current simple dashboard access model unless the project
separately approves a shared authentication integration. Authentication must not
expand into a new identity platform inside this plan.

## 9. Observability and operations

Use structured logs with:

- request or run ID
- job and attempt IDs
- source and resource type
- target fingerprint, not secret credentials
- state transition
- duration
- retry decision
- publication and quarantine counts
- AI input fingerprint and run status, never full private prompts

Expose health summaries for:

- API liveness
- database readiness
- object-store readiness
- last successful scheduled run
- collection success and freshness
- failure and quarantine rate
- stale sources
- AI availability and capped usage

Do not introduce a new observability platform for the MVP. Start with Render
logs, database operational records, and the Operations screen.

## 10. Testing strategy

### 10.1 Backend unit tests

For every source, parser, service, formula, alert, and AI validator test:

- success
- permission denial
- rate limit
- timeout
- malformed response
- empty response
- pagination or continuation
- idempotent replay
- stale evidence
- quarantine
- duplicate processing
- missing required evidence
- unsupported AI claims and citations

### 10.2 Collector tests

- approved URL and domain enforcement
- timeout and resource cleanup
- CAPTCHA and challenge stopping
- no login-wall bypass
- browser start and close
- sanitized golden files
- seeded parser break
- geo and device metadata

### 10.3 PostgreSQL integration tests

- complete Alembic migration chain
- one Alembic head
- claim concurrency and lease fencing
- unique fingerprints
- cursor pagination
- transaction rollback
- idempotent publication
- Supabase-compatible connection behavior

### 10.4 Storage tests

- compressed content-addressed upload
- deduplication
- private bucket behavior
- signed URL expiry
- missing object behavior
- retention eligibility and deletion audit

### 10.5 Frontend tests

- navigation and responsive sidebar
- URL-backed filters
- loading, empty, stale, partial, quarantine, and error states
- charts with accessible text summaries
- evidence drawer
- source verification flow
- battle-card comparison
- AI draft accept, edit, and reject
- action and alert transitions
- important route-specific workflows

### 10.6 End-to-end tests

Use mocked external transports in normal CI:

1. Configure an approved universe fixture.
2. Plan and claim a collection job.
3. Store raw evidence.
4. Parse and publish observations.
5. Calculate a metric.
6. Create a scorecard gap.
7. Produce a deterministic action and safe AI draft.
8. Display it in the frontend.
9. Accept and complete the action.
10. Record an impact snapshot.

Live tests remain opt-in, credentialed, source-specific, and rate-limited.

### 10.7 Required verification commands

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy apps\backend\src
.\.venv\Scripts\python.exe -m pytest
C:\nvm4w\nodejs\corepack.cmd pnpm typecheck:web
C:\nvm4w\nodejs\corepack.cmd pnpm test:web
C:\nvm4w\nodejs\corepack.cmd pnpm build:web
git diff --check
```

Also run migrations and PostgreSQL integration tests against Supabase or an
equivalent real PostgreSQL service before release.

## 11. Delivery phases

Each phase must end with a working vertical slice. Do not build all schemas
first and postpone user workflows.

### Phase 0: Scope and production foundation

#### Backend

- Audit existing models, routers, migrations, tests, source clients, and branch
  state.
- Record the current one-head migration baseline.
- Add Render-safe configuration validation.
- Configure Supabase PostgreSQL and private Storage in a non-production project.
- Add `render.yaml`, backend Dockerfile, and deployment commands.
- Add the direct CLI application and health checks.

#### Frontend

- Configure Vercel deployment and API URL.
- Add the shadcn and Tailwind foundation.
- Build the app shell, responsive sidebar, page header, status components,
  evidence drawer, and chart tokens.
- Preserve all existing working routes during migration.

#### Exit gate

- Vercel can call Render.
- Render can read and write Supabase PostgreSQL.
- Render can write, deduplicate, and sign a Supabase Storage object.
- One Alembic head exists.
- No production Redis or MinIO dependency remains.

### Phase 1: Database-backed scheduler and operations

#### Backend

- Extract Celery task orchestration into reusable synchronous entry services.
- Implement `collect-due`, bounded job claiming, lease fencing, retries, and exit
  codes.
- Add retention and source-verification commands.
- Configure the hourly Render cron job.
- Add structured run summaries.

#### Frontend

- Rebuild Operations and Settings with shadcn.
- Show source readiness, jobs, attempts, failures, quarantine, freshness,
  completeness, parser versions, and retention.
- Add capture-success and freshness charts.

#### Exit gate

- A scheduled Render run completes without Celery or Redis.
- Failed work retries without duplication.
- Concurrent claims cannot complete the same attempt.
- Operators can understand failures from the UI without database access.

### Phase 2: Universe and automatic setup

#### Backend

- Finalize competitors, products, tracked entities, battle cards, and tracking
  tiers.
- Add evidence-backed mapping proposals using deterministic similarity first.
- Add source verification and initial import requests.
- Keep human approval for competitor and battle-card additions.

#### Frontend

- Build the setup readiness flow.
- Rebuild Universe and Products with shadcn forms, tables, dialogs, and CSV
  validation.
- Add mapping proposal review and battle-card comparison.

#### Exit gate

- A user can configure the approved universe without database edits.
- Invalid imports explain row-level problems.
- Every mapping records comparison basis and reviewer decision.

### Phase 3: Amazon end-to-end intelligence

#### Backend

- Complete SP-API, Ads, Brand Analytics, Amazon SERP, and product-page scheduled
  ingestion.
- Store all raw evidence before parsing.
- Publish rank, sponsored placement, listing, price, offer, badge, and
  availability observations.
- Add visibility, ad presence, content, and commerce metrics.
- Add golden files, canaries, and seeded-break tests.

#### Frontend

- Complete Amazon keyword detail, battle cards, advertising, listing changes,
  and evidence views.
- Add rank, Share of Voice, price, daypart, and listing-change visualizations.

#### Exit gate

- A credentialed Amazon job runs from schedule to dashboard.
- Novel and competitor products appear from the same SERP capture.
- Challenge handling stops and records the attempt.
- Reprocessing is idempotent.
- Quarantined data cannot reach metrics.

### Phase 4: Google end-to-end intelligence

#### Backend

- Complete Search Console and public Google SERP scheduled ingestion.
- Implement the Google Ads client and normalized first-party performance.
- Validate the official Transparency Center integration boundary.
- Publish only supported public creative evidence.

#### Frontend

- Add Google keyword visibility and Search Console views.
- Add Google Ads performance and creative evidence.
- Keep attribution and sampled-presence caveats visible.

#### Exit gate

- Search Console, Google Ads, and public SERP evidence reach the UI through the
  normal pipeline.
- Unsupported Transparency Center automation remains visibly unavailable rather
  than replaced with unsafe collection.

### Phase 5: Meta end-to-end intelligence

#### Backend

- Complete Marketing API and Ad Library scheduled ingestion.
- Normalize Novel performance and public competitor creative evidence.
- Generate idempotent creative change events.

#### Frontend

- Add Meta performance and creative-library views.
- Add creative filters and activity timelines.

#### Exit gate

- Credentialed Novel performance and approved public competitor evidence reach
  the dashboard.
- Missing competitor performance remains unknown.

### Phase 6: Scorecard and decision loop

#### Backend

- Connect published observations to versioned seven-dimension scorecards.
- Implement unknown and stale gating.
- Generate gaps, action drafts, alerts, and impact schedules.
- Add the evidence-constrained AI provider and deterministic fallback.

#### Frontend

- Build the Overview, Scorecards, Actions, and Alerts workflows.
- Add heatmaps, trend charts, evidence drawers, AI-draft review, and impact
  visualization.

#### Exit gate

- A real published observation can produce a scorecard, gap, draft action,
  alert, and visible evidence without manual database work.
- AI cannot publish unsupported claims or activate an action.
- The workflow still works with AI disabled.

### Phase 7: Hardening and controlled pilot

#### Platform

- Run Supabase migration and query-plan checks.
- Validate Vercel, Render API, Render cron, and Supabase Storage together.
- Apply retention and data-quality thresholds.
- Add production runbooks and rollback steps.
- Complete legal approval for public collection.

#### Pilot

- Configure the approved Amazon universe and keyword tiers.
- Connect Novel-owned Amazon, Google, and Meta accounts.
- Run a seven-day controlled pilot.
- Review daily collection health and action usefulness.
- Record failed, quarantined, stale, and unknown outcomes honestly.

#### Exit gate

- At least 98% scheduled capture success for the agreed pilot scope.
- T1 freshness is at most 60 minutes.
- A seeded parser break is caught before publication.
- Users complete the normal decision workflow without database edits.
- Every displayed critical value has inspectable evidence.
- Remaining unsupported sources and live limits are documented.

## 12. CI and deployment

### 12.1 Pull-request CI

- Ruff
- mypy
- backend unit and mocked integration tests
- frontend typecheck and tests
- frontend production build
- migration graph and offline SQL generation
- `git diff --check`
- secret scan

### 12.2 Deployment order

1. Apply reviewed migrations to Supabase.
2. Deploy the Render API.
3. Run API readiness checks.
4. Deploy the Render cron command disabled or with zero eligible work.
5. Deploy Vercel.
6. Verify the user workflow.
7. Enable one source and a small approved target set.
8. Expand only after collection health is proven.

### 12.3 Rollback

- Frontend: restore the previous Vercel deployment.
- API: restore the previous Render deployment.
- Cron: disable schedule before rollback.
- Database: prefer forward fixes; use downgrade only for migrations explicitly
  proven reversible.
- Publication: quarantine affected parser versions and republish from retained
  raw evidence after correction.

## 13. Product acceptance criteria

The MVP is complete only when:

1. Users can configure the approved universe and verify sources without database
   edits.
2. Amazon, Google, and Meta owned integrations have successful credentialed
   source runs.
3. Approved Amazon and Google public collection stops on challenges.
4. Raw evidence is stored before parsing and is inspectable through signed URLs.
5. Parsers are versioned, tested, and protected by quarantine and canaries.
6. Scheduled collection is idempotent and survives individual job failure.
7. Important metrics display source, freshness, confidence, and truth label.
8. Amazon keyword views show organic and sponsored competitors from the same
   capture.
9. Novel advertising performance keeps platform attribution definitions clear.
10. Competitor Meta and Google creative data contains only official published
    evidence.
11. Seven-dimension scorecards show unknown when required evidence is missing.
12. Lagging cells create evidence-backed gaps and draft actions.
13. AI explanations cite only supplied evidence and remain clearly marked drafts.
14. AI failure does not block deterministic recommendations or the user workflow.
15. Users can assign, complete, and inspect 7/14/30-day action impact.
16. Alerts can be acknowledged and resolved with an audit trail.
17. The frontend has clear loading, empty, stale, partial, quarantine, and error
    states.
18. Charts have accessible summaries and do not hide exact underlying values.
19. Vercel, Render, and Supabase are the only required production platforms.
20. PostgreSQL migrations, backend tests, frontend tests, type checks, and the
    production build pass.

## 14. Definition of done for every slice

A slice is done only when:

- the normal user workflow works without manual database edits
- raw evidence and lineage are present
- missing and stale data are safe
- retry and replay are idempotent
- expected failures are visible and useful
- backend and frontend contracts agree
- automated tests cover success and failure
- PostgreSQL behavior is verified when storage changes
- live capability has a real credentialed proof
- documentation and operational notes are current
- limits are stated plainly

## 15. First implementation sequence

Begin in this order:

1. Phase 0 production foundation.
2. Phase 1 database scheduler and Operations screen.
3. Phase 2 setup and universe workflow.
4. Phase 3 Amazon vertical slice.
5. Phase 4 Google vertical slice.
6. Phase 5 Meta vertical slice.
7. Phase 6 scorecard, AI explanation, and action loop.
8. Phase 7 controlled pilot and hardening.

Do not start the AI layer, cross-channel overview, or visual polish before the
source-to-publication path is reliable. Do not call any source live until a
credentialed run succeeds in the deployed environment.
