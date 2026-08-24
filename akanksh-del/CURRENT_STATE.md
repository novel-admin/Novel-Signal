# Current Repository State for Akanksh

Reviewed against `main` at commit `e05e69b` on 24 August 2026.

## What already exists

### S1 Universe

Use `apps/backend/src/novel_signal/modules/universe/`.

It already contains:

- Competitors, Novel products and competitor products
- Amazon marketplace identity fields
- Battle cards and battle-card items
- Archive and restore flows
- CSV templates, dry runs, import and export
- Pagination and validation
- Backend integration tests
- A working frontend at `apps/web/app/universe/`

Do not replace these models. Extend them only when a required collection target cannot be represented.

### S2 Keywords

Use `apps/backend/src/novel_signal/modules/keywords/`.

It already contains:

- Keyword records and normalized keyword text
- Source records
- Intent and tracking-tier fields
- Tracking targets
- Bulk updates
- CSV import and export
- Backend APIs and a frontend at `apps/web/app/keywords/`

Missing:

- Automated imports from Brand Analytics, Amazon Ads search terms and Google Search Console
- Source-run lineage and idempotent upserts
- Search-volume history and trend
- Keyword clustering automation
- Reverse-ASIN observations
- Amazon and Google Share of Voice
- Keyword gap calculation
- Revenue-at-stake inputs

### S3 Rank and Visibility

Use `apps/backend/src/novel_signal/modules/rank_visibility/`.

It already stores SERP captures and result rows and exposes rank history, visibility, brand presence, badge events and new entrants. The frontend exists at `apps/web/app/rank-visibility/`.

Missing:

- A real Amazon SERP collector
- A Google organic SERP source and platform field support where needed
- Scheduled ingestion
- Mobile and desktop collection profiles
- Pincode and geo execution
- Proven hourly runs

### S5 Listings

Use `apps/backend/src/novel_signal/modules/listings/`.

Snapshots, history, comparisons, completeness and change records already exist. The frontend is at `apps/web/app/listing-intelligence/`.

Missing:

- Amazon product-page parser and live ingestion
- Image hashes, A+ content and variation-family extraction where absent
- Competitor website page snapshots
- Automatic before/after change generation from collection runs

### S6 Price Monitoring

Use `apps/backend/src/novel_signal/modules/price_monitoring/`.

Price observations, seller offers, events, history, metrics and direct product comparisons already exist. The frontend is at `apps/web/app/price-monitoring/`.

Missing:

- Live Amazon price and offer parsing
- Price-per-unit normalization using pack quantity and unit
- Coupon, deal window, Buy Box and availability capture where visible
- Pincode-specific observations
- Scheduled change detection and downstream event publication

### S12 Collection

Use:

- `apps/backend/src/novel_signal/modules/collection/`
- `apps/backend/src/novel_signal/tasks/collection.py`
- `apps/backend/src/novel_signal/collectors/`
- `apps/backend/src/novel_signal/parsers/`

The repository already has job, attempt, failure, raw-evidence, parser-version, quarantine and data-quality foundations. Celery tasks and an executor registry exist.

The major gap is that no real Playwright executor is registered. `collectors/base.py` and `parsers/base.py` are contracts only.

### Source adapters

These are stubs and need full implementation:

- `sources/amazon/sp_api.py`
- `sources/amazon/brand_analytics.py`
- `sources/google/search_console.py`

`sources/amazon/ads_api.py` is implemented separately and belongs to Palguna for this delivery.

## Frontend condition

- The overview page is static and says data is not configured.
- Universe, keywords, collection, rank, listing and price screens exist.
- The generic products and sources pages are still scaffolded.
- Screens need freshness, confidence and evidence links before release.

## Verification condition

Confirmed locally:

- Frontend: 12 tests passed.
- TypeScript typecheck passed.
- Ruff passed.
- Strict mypy passed across 117 source files.
- Focused backend unit and API tests passed.

Not confirmed:

- Full PostgreSQL integration suite. Docker Desktop was unavailable and PostgreSQL tests waited indefinitely.
- Any live Amazon, Google Search Console or Playwright run.
- Browser installation and production worker execution.
- A continuous one-hour or one-day collection run.
