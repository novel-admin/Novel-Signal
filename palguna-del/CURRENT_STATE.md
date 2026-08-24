# Current Repository State for Palguna

Reviewed against `main` at commit `e05e69b` on 24 August 2026.

## What already exists

### Amazon Ads source

`apps/backend/src/novel_signal/sources/amazon/ads_api.py` contains a raw-first asynchronous client with:

- LWA token refresh
- Profile verification
- Pagination
- Permission and rate-limit errors
- Raw response fingerprints
- Mocked transport tests

Missing:

- Confirmation that endpoints and report workflows match the currently approved Amazon Ads API version
- Profile-specific request headers where required
- Asynchronous report creation and polling for performance/search-term data where required
- Connection to S12 jobs, raw evidence and parser versions
- Normalization into own-ad performance and S2 keyword handoff records
- Live credential proof

### S4 Ads

Use `apps/backend/src/novel_signal/modules/ads/`.

It already contains models and APIs for:

- Ad observations
- Daily ad presence
- Daypart profiles
- Creatives
- External ad records
- Spend estimates
- Novel-owned ad performance

The `/sync` route is not a proven end-to-end live synchronization flow. No complete S4 frontend exists.

### S7 Reviews

Use `apps/backend/src/novel_signal/modules/reviews/`.

It already contains review observations, topic records, topic trends and simple service logic. It has basic backend tests.

Missing:

- Live review observation handoff from Akanksh's public Amazon collection
- Rating distribution and review-velocity calculations
- Strong topic taxonomy and trend calculations
- Evidence/publication checks
- A user-facing review intelligence screen

### S8 Market Share

Use `apps/backend/src/novel_signal/modules/market_share/`.

It already contains CRUD-style models and APIs for model fits, unit estimates, daily share and backtests.

Missing:

- A real calibration pipeline using Novel first-party observations
- Scheduled estimation
- Confidence calculation based on input quality
- A market-share screen
- Proven backtests

### S9 Scorecards

Use `apps/backend/src/novel_signal/modules/scorecards/`.

It stores scorecard cells and history and assigns simple bands.

Missing:

- Automatic computation from latest published observations
- Complete dimensions required by the product
- SKU battle-card rollups
- Evidence and freshness handling
- A scorecard screen

### S10 Actions

Use `apps/backend/src/novel_signal/modules/actions/` and the frontend routes:

- `apps/web/app/changes/`
- `apps/web/app/actions/`

Change events, gaps, actions, transitions, history and 7/14/30-day impact records already exist.

Missing:

- Automatic gap generation
- Root-cause classification
- Revenue-at-stake ranking
- Recommended actions
- Automatic impact measurement

### S11 Alerts

`apps/backend/src/novel_signal/modules/alerts/router.py` is only a scaffold. There are no alert models, rule evaluation, persistence or usable frontend.

### Main frontend

- Overview is static and shows “Not configured”.
- Changes, actions and operations routes exist.
- There are no complete S4, S7, S8, S9 or S11 screens.
- Shared navigation does not represent the final product workflow.

## Verification condition

Confirmed locally:

- Frontend: 12 tests passed.
- TypeScript typecheck passed.
- Ruff passed.
- Strict mypy passed across 117 source files.
- Focused backend unit and source-client tests passed.

Not confirmed:

- Full PostgreSQL suite because Docker Desktop was unavailable.
- Live Amazon Ads ingestion.
- Scheduled intelligence processing.
- End-to-end data from a real source through scorecard, gap, action and alert.
- Production frontend build in this audit.
