# Novel Signal Engineering Guide

## Purpose

Novel Signal is an evidence-first competitive intelligence product.
It compares Novel products with competitors across marketplaces, search,
advertising, public websites, reviews, pricing, availability, and content.

The product must answer:

1. What are competitors doing?
2. How is Novel performing against them?
3. What changed?
4. How reliable and fresh is the evidence?
5. What should the team do next?

## Start Every Task Correctly

- Read `Novel_signal.md` for product requirements.
- Read the relevant delivery or design documents before coding.
- Inspect the current implementation, migrations, tests, Git branch, and remote.
- Treat current code as evidence; do not rely only on plans or old reports.
- Preserve unrelated worktree changes.
- Confirm current scope, owner, handoff, and acceptance criteria.
- Do not implement excluded sources or integrations without approval.

## Module Boundaries

- S1: Universe and Competitor Setup
- S2: Keyword Intelligence
- S3: Rank and Visibility Tracking
- S4: Ad Intelligence
- S5: Listing and Content Intelligence
- S6: Price, Promo, Offer, and Availability Intelligence
- S7: Reviews and Voice of Customer
- S8: Sales and Market Share Estimation
- S9: Benchmarking Scorecards
- S10: Gaps and Actions
- S11: Alerts and War Room
- S12: Collection Infrastructure

Keep each module focused on its own responsibility.
Use explicit schemas and APIs for cross-module communication.
Do not create duplicate models, tables, adapters, or migrations.
Follow ownership defined in the active delivery documents.
Shared contracts and migrations require review from affected owners.

## Source and Collection Rules

- Use official APIs before page collection.
- Collect only approved public, logged-out pages.
- Respect source terms, robots directives, and rate limits.
- Use conservative concurrency, delays, retries, jitter, and backoff.
- Never bypass CAPTCHA, login walls, bot detection, or access controls.
- Record a challenge as a collection failure and stop that attempt.
- Do not collect personal data unless explicitly approved and required.
- Hash public reviewer identity and never expose it in product responses.
- Keep collectors limited to configured domains, entities, keywords, and URLs.
- Close browser contexts, files, clients, and database sessions reliably.
- Never claim a source is live until a real credentialed run succeeds.

## Evidence-First Data Flow

Use this flow for every source:

`source -> raw evidence -> versioned parser -> validation -> publication -> metrics`

- Store raw responses before parsing or normalization.
- Raw evidence is immutable and content-addressed where possible.
- Keep collection attempts even when content is deduplicated.
- Parsers must be versioned and independently testable.
- Quarantine malformed, incomplete, or suspicious output.
- Never let quarantined data reach metrics, scorecards, gaps, or alerts.
- Reprocessing the same evidence must be idempotent.
- Normalized observations are immutable historical facts.
- Changes create new observations and change events; they do not rewrite history.

Every published observation should include:

- source type
- observed and collected timestamps
- raw evidence reference
- parser version
- publication status
- confidence label
- geo and device when relevant
- quarantine reason when rejected

## Truth and Confidence

- Label values as measured, derived, estimated, or unknown.
- Never display an estimate as a measured fact.
- Estimates must show a range, confidence, model version, and inputs.
- Do not invent missing search volume, competitor spend, sales, or revenue.
- Missing or stale values remain unknown; they do not become zero.
- Refuse to calculate when required evidence is insufficient.
- Every score, gap, action, and alert must link to inspectable evidence.

## Backend Practices

- Use Python 3.12+, FastAPI, Pydantic, SQLAlchemy, and Alembic patterns already present.
- Keep routers thin: validation and HTTP mapping only.
- Put business rules in services and persistence logic in repositories.
- Use typed request and response schemas.
- Enable `from_attributes` for ORM-backed response models.
- Use explicit domain errors and map expected failures to useful 4xx responses.
- Bound pagination and use deterministic ordering.
- Make external calls asynchronous and apply explicit timeouts.
- Handle permission, rate-limit, timeout, malformed response, and empty response cases.
- Do not log tokens, credentials, signed URLs, or sensitive raw payloads.
- Keep source clients raw-first; normalization belongs in parsers and services.
- Prefer small focused files over large multi-purpose modules.

## Database and Job Practices

- Keep one Alembic head.
- Inspect existing models and migrations before adding a table or column.
- Make migrations reversible where practical and safe for existing data.
- Use database constraints for identity, uniqueness, and valid relationships.
- Use deterministic fingerprints for idempotent events, gaps, and alerts.
- Workers must record attempts, failures, retries, and terminal state.
- Retries must not duplicate observations or actions.
- Scheduled jobs must use explicit tier, freshness, and concurrency rules.
- Do not treat SQLite tests as proof of PostgreSQL behaviour.
- Run migration tests against PostgreSQL before release.

## Frontend Practices

- Use the existing Next.js, React, and TypeScript structure.
- Reuse current API helpers and visual patterns.
- Do not add a new UI framework or state library without approval.
- Build around user questions, not internal table names.
- Provide clear loading, empty, stale, quarantined, and error states.
- Show source, freshness, confidence, and evidence access near important values.
- Keep filters in the URL when users need shareable views.
- Use accessible labels, keyboard controls, headings, tables, and status messages.
- Never label fixture, static, or manually inserted data as live.

## API and Handoff Compatibility

- Prefer additive API changes.
- Coordinate renamed or removed fields with every consumer.
- Update backend schemas, frontend types, tests, and documentation together.
- Publish observations through agreed contracts, not direct cross-module table writes.
- A module should not know collector or parser internals.
- Include example request and response payloads for new shared endpoints.

## Testing Requirements

- Add tests with every behaviour change.
- Use mocked external transports in normal CI.
- Keep live API tests opt-in and clearly marked.
- Keep sanitized golden files for page parsers.
- Test success, permission denial, rate limits, timeouts, malformed data, and empty data.
- Test idempotency, stale data, quarantine, and duplicate processing.
- Test important calculations with explicit expected values.
- Test user-visible error and partial-data states.
- A passing build does not prove route-specific workflows; test them directly.

Run before merging:

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy apps\backend\src
.\.venv\Scripts\python.exe -m pytest
C:\nvm4w\nodejs\corepack.cmd pnpm typecheck:web
C:\nvm4w\nodejs\corepack.cmd pnpm test:web
C:\nvm4w\nodejs\corepack.cmd pnpm build:web
```

Also verify migrations against PostgreSQL and confirm one Alembic head.

## Git and Delivery Discipline

- Use focused branches and commits.
- Do not commit secrets, credentials, raw customer data, or generated caches.
- Do not overwrite, reset, or delete unrelated user changes.
- Commit only files within the approved task scope.
- Run `git diff --check` before committing.
- Report tests actually run and clearly state anything not verified.
- Separate foundation, fixture-backed capability, and live verified capability.
- Do not exaggerate progress or production readiness.

## Definition of Done

A feature is done only when:

1. The normal user workflow works without manual database edits.
2. Data has evidence, lineage, freshness, and confidence.
3. Failure and partial-data behaviour is visible and safe.
4. Reprocessing is idempotent.
5. Relevant automated tests pass.
6. PostgreSQL migrations are valid when storage changed.
7. Frontend and backend contracts agree.
8. Live capability has a real source-backed verification.
9. Documentation and operational notes are updated.
10. Remaining limits are stated plainly.
