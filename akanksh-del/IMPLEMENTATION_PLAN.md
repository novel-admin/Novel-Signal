# Akanksh Detailed Implementation Plan

Work in small vertical slices. Each source must go from credential check to raw evidence to normalized records to a visible screen before starting another source.

## A1. Stabilize S1 tracking inputs

Reuse the current universe models and APIs.

Tasks:

1. Confirm each Novel product can store ASIN, product URL, pack quantity, unit, brand and category.
2. Confirm each competitor product can store ASIN, product URL, competitor, tracking tier and category.
3. Confirm battle cards map one Novel SKU to multiple direct competitor SKUs.
4. Add configured public domains and URLs for competitor website tracking. Keep these as explicit allowlisted targets.
5. Add geo profiles for priority pincodes and device profiles if the existing S3 structures cannot represent them.
6. Add a validation endpoint or readiness report showing unmapped products, missing ASINs, missing URLs and battle cards with no competitors.
7. Extend CSV import/export for any new required fields.

Acceptance:

- A category manager can import Novel SKUs, competitors and battle cards without direct database access.
- Invalid ASINs, duplicate marketplace identities and broken mappings are rejected clearly.
- Every active tracking target resolves to a product, keyword, URL, tier and collection schedule.

## A2. Implement Amazon SP-API

Implement `apps/backend/src/novel_signal/sources/amazon/sp_api.py` using the existing `SourceAdapter` contract.

Required resources for V1:

- Catalog/listing information for Novel ASINs
- Current inventory and availability for Novel products
- Current price and offer information for Novel products
- Orders or sales summaries needed for later calibration, limited to granted permissions

Tasks:

1. Implement LWA token refresh and AWS request signing.
2. Add marketplace and region headers.
3. Implement pagination and report polling where required.
4. Handle 401/403, throttling, retry-after and expired report documents explicitly.
5. Return immutable `RawSourcePage` objects; do not normalize inside the client.
6. Add request fingerprints and source cursors.
7. Connect verification to `/api/v1/sources` so configured does not falsely mean connected.
8. Store raw responses before parsing.
9. Add parsers that publish owned listing, price and inventory observations.

Do not log tokens, secrets, signed URLs or raw credentials.

## A3. Implement Brand Analytics

Implement `sources/amazon/brand_analytics.py` through the permitted SP-API report workflow.

Required Week 1 reports, subject to account permission:

- Search Query Performance
- Search Catalog Performance where available
- Top Search Terms or equivalent permitted report

Tasks:

1. Request reports by date window and marketplace.
2. Poll asynchronously until complete, failed or timed out.
3. Download and retain the raw report document.
4. Parse query, rank, search volume/frequency rank, click share and conversion share fields available in each report.
5. Upsert keywords by normalized text.
6. Record a separate source row for every contribution.
7. Preserve report date, marketplace, ASIN, raw evidence ID and parser version.
8. Never combine values from different report definitions as if they were the same metric.

## A4. Implement Google Search Console

Implement `sources/google/search_console.py`.

Required dimensions:

- query
- page
- country
- device
- date

Required metrics:

- clicks
- impressions
- CTR
- average position

Tasks:

1. Parse service-account credentials from the secret setting without writing them to disk.
2. Verify every configured property.
3. Fetch rows in date windows with pagination.
4. Store raw JSON first.
5. Normalize queries into S2 source records and metric history.
6. Keep GSC metrics clearly labelled as Novel-owned website performance, not competitor web data.

## A5. Build Playwright collection

Create focused implementations under `collectors/` and `parsers/` rather than one large scraper.

Recommended files:

- `collectors/playwright_browser.py`
- `collectors/amazon_serp.py`
- `collectors/amazon_product.py`
- `collectors/google_serp.py`
- `collectors/public_web_page.py`
- `parsers/amazon_serp.py`
- `parsers/amazon_product.py`
- `parsers/google_serp.py`
- `parsers/public_web_page.py`

Collector rules:

1. Public, logged-out pages only.
2. One browser context per geo/device profile.
3. Conservative concurrency and configured delays.
4. Capture final URL, status, HTML, screenshot when useful, timestamp and challenge state.
5. Stop and record a failure on CAPTCHA, login wall or bot challenge.
6. Do not add challenge-solving, stealth bypass or account automation.
7. Allowlist domains and page types.
8. Close contexts and browsers on every failure path.

Amazon SERP parser output:

- keyword ID and captured query
- absolute and placement-specific position
- ASIN, brand and title
- organic or sponsored placement type
- price, MRP, coupon and deal label
- rating and review count
- badge
- delivery promise
- image hash
- capture time, pincode and device

Amazon product parser output:

- title, bullets and description
- images and image order hashes
- A+ presence and visible content
- video presence
- variation information
- category and BSR
- price, MRP, coupon, deals and offers
- Buy Box seller where public
- stock/availability and delivery promise
- rating and review count
- pack quantity and unit

Google SERP parser output:

- query, rank and result type
- title, URL and displayed domain
- snippet
- Novel or competitor identity match
- capture time, country/geo and device

Public competitor website output:

- URL, title, headings and selected visible product content
- content hash
- previous hash comparison
- changed fields or blocks

## A6. Connect S12 execution

Tasks:

1. Register executors for Amazon SERP, Amazon product, Google SERP and public website jobs.
2. Generate due jobs from active tracking targets and tiers.
3. Enforce T1 hourly, T2 every four hours and T3 daily for the Week 1 configuration.
4. Save a collection attempt before network work begins.
5. Save raw evidence before parsing.
6. Register parser versions and include them in every normalized record.
7. Quarantine schema failures and suspicious field-fill drops.
8. Deduplicate repeated responses by fingerprint without losing attempt history.
9. Update freshness, completeness and failure-rate checks.
10. Make collection operations visible on the existing collection and operations screens.

## A7. Complete keyword intelligence

Extend S2 without replacing the current keyword CRUD.

Required inputs:

- Brand Analytics
- Amazon Ads search-term handoff from Palguna
- Google Search Console
- Amazon search suggestions collected through approved public collection
- Terms observed in Amazon SERPs and listings
- Review phrases published by Palguna's S7 pipeline

Required capabilities:

1. Idempotent normalized keyword upsert.
2. Source lineage with first seen, last seen and source-specific metrics.
3. Intent classification: generic, attribute, problem/benefit, Novel brand, competitor brand and adjacent.
4. Manual correction of automated classifications.
5. Volume and trend history when a real source supplies it.
6. Tracking-tier assignment based on business priority, volume and volatility.
7. Reverse-ASIN map derived from observed organic and sponsored SERP presence.
8. Amazon organic, paid and total Share of Voice.
9. Google organic visibility share for configured Novel and competitor domains.
10. Organic, paid, coverage and efficiency gaps.
11. Evidence links from every gap to the underlying source observations.

Do not claim Google competitor search volume from Search Console. Do not create fake volumes for keywords with no measured source.

## A8. Publish S3, S5 and S6

For every successful parse:

1. Publish S3 captures and result rows atomically.
2. Publish S5 listing snapshots and calculate field-level diffs.
3. Publish S6 price and offer observations.
4. Calculate price per unit only when quantity and unit are valid.
5. Emit idempotent change events for rank, badge, listing, price, offer and availability changes.
6. Include raw evidence ID, parser version, observation time, source, confidence and publication state.
7. Hand events to Palguna's scorecard, action and alert processing.

## A9. Finish Akanksh-owned screens

Update these routes:

- `/universe`
- `/keywords`
- `/collection`
- `/rank-visibility`
- `/listing-intelligence`
- `/price-monitoring`
- `/products`
- `/sources`

Every data screen must show:

- Last successful collection time
- Fresh, stale or failed status
- Source
- Measured, derived or estimated label
- Link to raw evidence or capture details where permitted
- Useful empty, loading and error states

## A10. Live handoff

Before handoff to Palguna:

1. Run one configured Novel SKU and at least three competitor ASINs end to end.
2. Run at least ten keywords through Amazon desktop, Amazon mobile and Google organic collection.
3. Demonstrate one listing change fixture and one price change fixture.
4. Export the normalized API payloads described in `DATA_CONTRACTS.md`.
5. Record unresolved API permission limits honestly.
