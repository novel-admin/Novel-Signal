# Akanksh Testing and Definition of Done

## Automated tests

### Source adapters

For SP-API, Brand Analytics and GSC test:

- successful authentication
- rejected credentials
- missing permission
- pagination
- throttling and retry-after
- timeout
- malformed JSON or report data
- empty valid response
- duplicate reprocessing
- secret redaction

Use mocked transports for normal CI. Keep live tests opt-in and clearly marked.

### Playwright collectors

Test:

- browser and context cleanup
- desktop and mobile profiles
- pincode/geo input
- normal page capture
- redirect handling
- timeout
- CAPTCHA/challenge detection
- login wall detection
- blocked response
- allowlist rejection

No test or production code may solve or bypass a challenge.

### Parsers

Maintain committed sanitized golden files for:

- Amazon search results
- Amazon product page
- Google organic results
- competitor public website page

Each parser test must cover:

- expected fields
- missing optional fields
- changed layout fixture
- duplicate rows
- invalid money and quantity
- suspicious field-fill drop
- quarantine behavior

### Modules

Test:

- S1 import, mapping and readiness
- S2 idempotent source merge, classification, SOV and gaps
- S3 rank history and same-capture comparison
- S5 immutable snapshots and field-level diffs
- S6 price-per-unit, offer history and change events
- S12 retries, dead-letter behavior, raw-first persistence and quality checks

## Required commands

Run from repository root:

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy apps\backend\src
.\.venv\Scripts\python.exe -m pytest
C:\nvm4w\nodejs\corepack.cmd pnpm typecheck:web
C:\nvm4w\nodejs\corepack.cmd pnpm test:web
C:\nvm4w\nodejs\corepack.cmd pnpm build:web
```

Also run:

```powershell
docker compose -f infra\compose.yaml up -d postgres redis minio
.\.venv\Scripts\python.exe -m alembic -c apps\backend\alembic.ini upgrade head
.\.venv\Scripts\python.exe -m alembic -c apps\backend\alembic.ini heads
```

There must be one Alembic head.

## Live acceptance dataset

Minimum Week 1 proof:

- At least 5 Novel SKUs
- At least 3 mapped competitors per Novel SKU
- At least 10 T1 keywords
- Amazon desktop and mobile captures
- At least 2 configured pincodes where supported
- At least 1 Google Search Console property
- At least 3 configured competitor domains

## Definition of done

Akanksh's delivery is done only when:

1. All three owned API connections are live and show clear permission failures.
2. Playwright captures public pages and backs off on challenges.
3. Raw evidence is stored before any record is published.
4. Reprocessing is idempotent.
5. S2 builds a usable keyword universe from all available approved sources.
6. Amazon and Google rank visibility can be compared by keyword.
7. Listing and price differences can be viewed by SKU battle card.
8. Every value shows source, observation time, freshness and confidence.
9. PostgreSQL migrations and automated tests pass.
10. Palguna can consume the published contracts without reading scraper internals.

## Not acceptable as completion

- A source marked configured without a successful live verification
- Fixture-only proof described as live capability
- Data written directly to dashboards without raw evidence
- Silent parser failure
- Fake keyword volume or competitor performance data
- One successful manual script that is not connected to S12 scheduling
