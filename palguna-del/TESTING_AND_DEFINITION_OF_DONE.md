# Palguna Testing and Definition of Done

## Automated tests

### Amazon Ads

Test:

- successful token and profile verification
- incorrect profile permission
- report creation, polling and completion
- failed and expired reports
- pagination
- throttling and retry-after
- malformed and empty reports
- raw-first persistence
- duplicate report reprocessing
- secret redaction

Live tests must be opt-in and must not run in normal CI.

### S4

Test:

- sponsored observation ingestion
- continuous and broken ad-presence days
- total ad days
- keyword breadth
- slot share and average position
- daypart grouping
- missing capture periods
- measured versus derived labels

Never treat a missing capture as proof that a competitor was not advertising.

### S7

Test:

- review-count deltas
- review velocity with missing days
- rating trajectory
- topic extraction
- sample-size confidence
- reviewer identity removal/hashing
- unpublished input rejection

### S8

Test:

- minimum evidence gate
- model version persistence
- confidence range
- stale input rejection
- backtest error
- refusal to estimate when evidence is insufficient

### S9-S11

Test:

- each scorecard formula
- unknown input handling
- score history
- deterministic gap generation
- duplicate gap prevention
- action lifecycle rules
- 7/14/30-day impact scheduling
- alert threshold evaluation
- alert deduplication
- acknowledge and resolve flow
- evidence links

### Frontend

Test:

- overview with live data, partial data and no data
- SKU comparison
- scorecard unknown/stale states
- gap-to-action flow
- alert acknowledgement
- API error handling
- keyboard-accessible controls and table labels

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

## End-to-end acceptance

Using the shared Week 1 dataset:

1. Open the overview and select a Novel SKU.
2. View its mapped competitors and current freshness state.
3. Inspect Amazon and Google rank visibility.
4. Inspect Amazon sponsored presence and Novel's measured ad performance.
5. Compare price, listing quality, reviews and availability.
6. Open a Lagging scorecard cell and inspect its evidence.
7. Create or open the generated gap and action.
8. Assign the action, set a due date and transition its status.
9. Acknowledge the linked alert.
10. Confirm quarantined or stale evidence does not affect the score.

## Definition of done

Palguna's delivery is done only when:

1. Amazon Ads runs live and stores raw evidence before normalization.
2. Competitor Amazon ad presence is calculated from same-capture sponsored results.
3. Review trends are evidence-backed.
4. Estimates either show ranges and confidence or clearly refuse to run.
5. Every configured SKU has a scorecard with values or explicit unknown states.
6. Lagging cells create inspectable gaps.
7. Actions have owners, due dates, status history and impact measurement support.
8. Alerts are persisted, deduplicated and actionable in the product.
9. The overview answers how Novel performs against competitors without manual database inspection.
10. PostgreSQL migrations, backend tests, frontend tests, typecheck and production build pass.

## Not acceptable as completion

- Calling fixture data live
- Exact competitor spend, units or revenue without evidence and confidence ranges
- Treating missing observations as zero presence
- Scorecards built from quarantined or stale records
- Static dashboard cards labelled as working features
- Manual database inserts required for the normal user journey
