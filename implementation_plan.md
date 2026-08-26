# Novel Signal MVP implementation plan

## 1. Scope and outcome

Build the evidence-first Novel Signal platform described in `Novel_signal.md` using the existing Render backend, Vercel frontend, and Supabase database.

In scope:

- Amazon SP-API for seller catalog, orders, inventory, pricing, offers, and reports.
- Amazon Ads API for Novel campaign performance and approved advertising reports.
- Amazon public, logged-out page collection for competitor search, listings, offers, and ads where permitted.
- Google Ads API for Novel account, campaign, keyword, search-term, and performance data.
- Meta Marketing API for ad-account, campaign, ad-set, ad, and Insights data.
- Manual competitor URL/product collection with safe web scraping and challenge handling.
- S1–S12 workflows: universe, keywords, rank, ads, content, price/availability, reviews, sales estimates, scorecards, gaps/actions, alerts, and collection operations.
- Email/password authentication, workspace isolation, user-managed provider credentials, scheduled collection, and a manual Resync action.
- A clean shadcn-based dashboard with tables, charts, freshness, confidence, evidence links, and error states.

Out of scope for this MVP: conversational assistant, additional ad/marketplace integrations, automatic competitor spend or sales claims, CAPTCHA/login bypass, and direct mutation of provider campaigns or listings.

## 2. Non-negotiable data contract

Every source follows:

```text
source -> raw evidence -> versioned parser -> validation -> publication -> metrics
```

Raw provider responses are stored before normalization. Evidence is immutable, content-addressed where practical, and linked to every published observation. Parser versions, collection timestamps, observed timestamps, source, geo/device, confidence, and publication status are required. Invalid, incomplete, stale, challenged, or suspicious data is quarantined and cannot feed metrics, scorecards, gaps, or alerts. Reprocessing must be idempotent.

Values must be labelled measured, derived, estimated, or unknown. Missing data remains unknown, never zero. Sales, market share, competitor spend, and search volume are estimates only when the required inputs exist and the UI shows range, confidence, model version, and inputs.

## 3. Runtime architecture

### Backend (Render)

- FastAPI routers remain thin; services contain provider and domain rules; repositories contain SQLAlchemy persistence.
- Render web service runs the API. A Render Cron job invokes the collection scheduler hourly. A second Cron job runs daily retention and health checks. If volume requires it, add one Render background worker using the existing queue pattern; do not add another infrastructure product.
- Supabase PostgreSQL is the source of truth. Alembic must have one head and migrations must be tested against PostgreSQL.
- Provider clients use async HTTP, explicit timeouts, bounded retries, exponential backoff with jitter, rate-limit handling, and structured redacted logs.
- Secrets are encrypted at application level before storage. Decryption is server-only; the browser receives provider status, account labels, masked IDs, and last verification time only.

### Frontend (Vercel)

- Keep the existing Next.js/React/TypeScript structure and API helpers.
- Use existing shadcn components, Tailwind, Recharts (or the already installed chart component), and accessible forms/tables.
- Route protection must be enforced by backend session verification as well as frontend guards.
- Use URL query parameters for workspace, product, competitor, keyword, source, date range, and status filters.

## 4. Authentication, workspaces, and provider configuration

1. Add Supabase-backed `users`, `workspaces`, and `workspace_members` records. Store a password hash (PBKDF2/Argon2-compatible implementation), never a plaintext password. Seed `demo@demo.com` with `demo123` only in the demo workspace.
2. Issue an HttpOnly, Secure, SameSite session cookie after login. Add `GET /api/v1/auth/session`, login, logout, and password-change endpoints. Every protected router resolves the authenticated user and workspace membership server-side.
3. Add `source_connections` with provider (`amazon_sp`, `amazon_ads`, `google_ads`, `meta_ads`, `amazon_public`), status, account identifiers, scopes, last verified time, last sync time, and error summary.
4. Add encrypted `source_credentials` and a key-version field. Use an application encryption key from Render environment variables; support key rotation without exposing old plaintext values.
5. Build Settings > Integrations forms. Each provider has its own fields, save, Verify connection, Disconnect, and Resync controls. Show masked values and actionable typed errors. Never log or return secrets.
6. Verification performs a minimal real provider call and records success/failure evidence. A connection is not marked ready merely because credentials were saved.

### Provider setup details

**Amazon SP-API:** collect seller ID, marketplace IDs, LWA client ID/secret, refresh token, and AWS IAM role/access-key configuration required by the selected SP-API authorization model. Exchange the LWA refresh token for an access token at runtime; tokens are short-lived. Use the correct regional endpoint, `x-amz-access-token`, marketplace headers, and SigV4 signing where required. Verify with a low-cost seller/account request.

**Amazon Ads:** collect profile/account ID, client ID/secret, and refresh token. Discover profiles, select the profile and marketplace, verify with a small report request, and persist the report scope. Treat report data as delayed and show provider freshness rather than presenting it as real-time.

**Google Ads:** implement OAuth authorization-code flow with offline access. Store the refresh token, login customer ID, selected customer ID, developer-token configuration, and scopes. On callback, exchange the code, encrypt the refresh token, discover accessible customers, and verify with a small GAQL query. Store API version and query version with each capture.

**Meta Ads:** collect system-user/user access token, ad-account ID, app configuration, and selected scopes (`ads_read` for read-only MVP; `ads_management` only if later approved). Verify through the account and Insights endpoints. Store cursor and attribution settings for each report.

## 5. Provider ingestion adapters

All adapters return a common raw capture envelope and do not write domain tables directly.

### Amazon SP-API and Ads

- Build typed clients for catalog/products, listings, orders, inventory, pricing/offers, reviews where available, and reports.
- For asynchronous reports: create report, persist report ID, poll status with backoff, retrieve report document, download the document, hash the bytes, and only then parse it. Keep every attempt and provider status.
- Persist marketplace, seller/profile, report type, requested interval, report document ID, compression/encoding, and provider timestamps.
- Normalize ASIN, SKU, parent/child relationships, price, currency, buy-box/offer, stock, orders, units, spend, impressions, clicks, conversions, and sales into source-specific observations.
- Use Amazon public pages only for configured URLs/search terms and logged-out access. Capture HTML, response metadata, and screenshots/structured snippets where allowed. Stop on CAPTCHA, login walls, bot challenges, or robots restrictions and record a collection failure.

### Google Ads

- Use GAQL with explicit field lists and a versioned query registry. Start with customer, campaign, ad group, keyword view, search-term view, and daily campaign/ad-group performance.
- Use SearchStream for bounded report jobs and Search with page tokens where pagination is preferable. Persist request query, customer ID, API version, page/chunk number, and raw response.
- Store metrics such as impressions, clicks, cost micros, conversions, conversion value, CTR, CPC, and search-term text with the provider segment date. Convert cost micros only in the parser and retain the original integer.
- Handle OAuth expiry, permission denial, developer-token limits, rate limits, partial failures, empty result sets, malformed JSON, and schema changes as typed capture outcomes.

### Meta Marketing API

- Use the account, campaigns, ad sets, ads, and Insights edges with explicit fields and date ranges. Persist `paging.next` cursors and stop at a bounded page count.
- Store account timezone, attribution setting/window, breakdowns, action-value arrays, spend, impressions, reach, clicks, CTR, CPM, CPC, conversions, and conversion value without flattening away the original action type.
- Use asynchronous Insights jobs for larger ranges: create job, poll status, download results, and persist job IDs and raw pages. Mark incomplete jobs as partial/quarantined, not successful.
- Map HTTP 401/403/429/5xx, invalid token, invalid account, expired job, empty response, and malformed response to typed errors with user-visible remediation.

## 6. Evidence, parsing, and publication

Create these shared records (reuse existing equivalents where present):

- `collection_jobs`, `collection_attempts`, `raw_evidence`, `parser_runs`, `quarantine_records`.
- `source_observations` with source, entity, metric, value, unit, observed/collected timestamps, evidence ID, parser version, confidence, geo/device, and publication status.
- `change_events` with deterministic fingerprint, before/after references, evidence IDs, and detected timestamp.

Processing rules:

1. Compute a stable request/entity/time-window fingerprint before collection.
2. Store the raw response even when its content duplicates an earlier response.
3. Parse with a versioned parser and validate required fields, enums, timestamps, currencies, IDs, and numeric bounds.
4. Quarantine malformed or incomplete data with a reason and retry classification.
5. Publish only validated observations. Never update historical observations in place.
6. Emit change events only after publication; deduplicate by fingerprint.
7. Expose evidence detail endpoints so a user can inspect source, timestamps, parser version, confidence, and the raw capture reference.

## 7. Universe and Novel configuration (S1–S2)

Provide guided setup for:

- Novel products: internal SKU, title, brand, category, ASIN/GTIN/marketplace IDs, target marketplace, and status.
- Competitors: brand, seller, product URL, ASIN/identifier, marketplace, tier, and notes.
- Tracked entities: product/variant relationships and source-specific IDs.
- Battle cards: 3–8 direct competitors per Novel SKU, with analyst accept/reject and rationale.
- Keywords: keyword text, locale, marketplace, device, intent, priority, Novel SKU, competitor association, and active status.

Auto-discovery may propose competitor products or keywords from configured searches, but an analyst must accept or reject proposals before they are collected as tracked entities.

## 8. Collection schedule and Resync

- Tier T1 (hourly): configured Amazon page-1 organic/sponsored rank and ad presence/daypart checks for priority keywords/products; provider API freshness checks.
- Tier T2 (every 4 hours): product detail/listing, price, offer, availability, and selected ad observations.
- Tier T3 (daily): reviews, content snapshots/diffs, sales/market-share estimates, scorecard refresh, competitor library checks, and retention.
- Every job has workspace, tier, source, entity set, window, idempotency key, attempt count, next retry, terminal state, and quality result.
- `POST /api/v1/collection/resync` accepts selected sources/entities and a bounded date range. It queues work and returns a job ID; `GET /api/v1/collection/jobs/{id}` reports progress and partial failures.
- The dashboard exposes readiness, freshness, failed/quarantined counts, provider rate limits, and last successful capture. A failed source must not hide successful sources.

## 9. Domain modules and calculations

- **S3 Rank/visibility:** organic and sponsored rank, page presence, share-of-voice, daypart, device, and geo; unknown when capture is missing or stale.
- **S4 Ads:** Novel campaign metrics from Amazon/Google/Meta plus public competitor ad presence/library evidence. Do not infer competitor spend.
- **S5 Listing/content:** title, bullets, images, A+, claims, ratings/review count, and versioned diffs.
- **S6 Price/promo/offer/availability:** price, currency, promotion, seller, buy box, stock/availability, and observation time.
- **S7 Reviews:** aggregate rating/count and hashed reviewer identity only when public collection is permitted; sentiment/topics are derived and evidence-linked.
- **S8 Sales/share:** estimates require documented inputs, range, confidence, and model version.
- **S9 Scorecards:** calculate the documented dimensions for every Novel SKU; use valid enum values and evidence links.
- **S10 Gaps/actions:** deterministic gap rules produce prioritized, explainable actions with owner/status and linked evidence.
- **S11 Alerts/war room:** threshold and change alerts with deduplication, severity, acknowledgement, snooze, and evidence links.
- **S12 Collection:** health, readiness, data quality, retention, failures, quarantine, raw evidence, and parser/run visibility.

## 10. Dashboard and frontend routes

Implement these routes with shared page shell, workspace selector, date/source filters, loading skeletons, empty states, stale/quarantined badges, and retry actions:

- `/login` and `/settings/integrations`: auth and credential setup/verification.
- `/dashboard`: KPI cards, scorecard distribution, visibility trend, ad spend/performance trend, price/availability changes, open gaps, alerts, and last sync status.
- `/universe`: Novel products, competitors, tracked entities, battle cards, and pending proposals.
- `/keywords`: keyword management, rank table, visibility chart, device/geo/daypart filters.
- `/ads`: Amazon, Google, Meta tabs; spend/impressions/clicks/conversions charts; campaign and keyword tables; competitor ad evidence.
- `/listings`, `/pricing`, `/reviews`, `/scorecards`, `/gaps`, `/alerts`.
- `/collection`: job timeline, readiness checks, data-quality/quarantine tables, raw-evidence links, and Resync dialog.

Every important metric shows source, observed time, collected time, confidence, freshness, and an evidence drawer. Fixture/demo records are visibly labelled as demo data and never presented as live.

## 11. AI use (bounded and evidence-first)

Use deterministic rules for scorecards, gaps, alerts, and provider normalization. AI is proposal-only for listing diff summaries, review/topic grouping, competitor candidate explanations, and action wording. Store model name/version, prompt/input evidence IDs, output, and confidence. Do not allow AI output to publish unsupported facts or overwrite observations.

## 12. Testing and acceptance

Backend tests cover auth/session/workspace isolation; encrypted credential storage; provider success, pagination, token refresh, permission denial, rate limits, timeouts, malformed and empty responses; report polling; parser versions; quarantine; idempotency; stale data; calculations; and API/frontend contract examples.

Frontend tests cover login/logout, protected routes, integration verification, Resync progress, filters, charts, empty/stale/error/quarantine states, and demo data labelling. Run the existing Ruff, mypy, pytest, web typecheck, web tests, and web build commands. Run migrations against PostgreSQL and verify one Alembic head.

Acceptance requires a new user to sign in, configure each provider from the UI, verify credentials, configure Novel products/competitors/keywords, run Resync, see published observations and evidence, and understand partial failures without database edits. The demo account shows seeded, schema-valid data only; live capability is claimed only after a real credentialed provider run succeeds.

## 13. Delivery sequence

1. Confirm current models, migrations, routes, tests, and existing worktree changes; reuse existing contracts.
2. Finish auth/workspace isolation and integration settings with encrypted credentials and typed verification.
3. Implement shared collection/evidence/quarantine pipeline and scheduler/Resync job tracking.
4. Implement Amazon SP-API, Amazon Ads, and safe public Amazon collection adapters.
5. Implement Google Ads OAuth/GAQL adapter and Meta OAuth/Insights adapter.
6. Complete S1–S8 normalized observations and S9–S12 calculations/operations.
7. Build the shadcn dashboard routes and evidence/freshness/error UX.
8. Seed schema-valid demo data, run the full test/migration suite, and perform opt-in credentialed canary runs for each provider.
9. Document deployment variables, OAuth redirect URLs, Render Cron commands, Supabase migration steps, provider permissions, rate limits, and known data-latency limits.

## Provider references

- Google OAuth: https://developers.google.com/google-ads/api/docs/oauth/user-authentication
- Google Ads Search/SearchStream: https://developers.google.com/google-ads/api/rest/common/search
- Amazon SP-API onboarding: https://developer-docs.amazon.com/sp-api/docs/onboarding-overview
- Amazon SP-API reports: https://developer-docs.amazon.com/sp-api/docs/reports-api-v2021-06-30-tutorial-request-a-report
- Amazon Ads API: https://advertising.amazon.com/en-ca/about-api
- Meta Marketing API collection and pagination examples: https://www.postman.com/meta/facebook-marketing-api/documentation/0zr4mes/facebook-marketing-api-mapi
