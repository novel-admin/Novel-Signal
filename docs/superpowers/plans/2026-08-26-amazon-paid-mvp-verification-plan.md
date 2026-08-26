# Amazon paid MVP implementation plan

## Product promise

A customer uploads Novel-owned Amazon.in SKUs and seed keywords. Novel Signal collects approved public Amazon evidence, discovers competing ASINs, and shows measurable rank, sponsored presence, price, listing, review, BSR, availability, change, gap, and action data.

## Definition of paid value

The demo is paid-product ready when a customer can complete this path without database edits:

`upload SKU CSV -> configure keywords and pincodes -> collect Amazon data -> review competitor candidates -> approve competitors -> open battle card -> inspect changes and evidence -> act on gaps`

## Delivery phases and proof gates

### P0: Access and deployment

- Environment-driven CORS.
- Vercel frontend points to backend `/api/v1`.
- Demo access code protects the dashboard and API.
- PostgreSQL URL supports the installed `psycopg` driver.

Proof: unauthenticated API returns 401, login works, Vercel preflight succeeds, and health remains public.

### P1: Customer and SKU onboarding

- CSV and manual Novel SKU onboarding.
- Amazon.in ASIN validation and duplicate protection.
- Seed keyword and tracking-tier configuration.
- Pincode and device configuration.
- Readiness screen before collection.

Proof: a new customer can upload a valid file, see imported products, and receive actionable validation errors for bad rows.

### P2: Real Amazon public collection

- Allowlisted logged-out Amazon.in search and product-page requests.
- HTTP first, Playwright only when needed.
- Desktop/mobile and pincode context.
- Conservative concurrency, delay, retry, and timeout policy.
- Raw HTML/screenshot persistence before parsing.
- Challenge, login-wall, blocked, timeout, empty, and malformed-response handling.

Proof: one real approved search and product capture is stored, retrievable, and linked to a collection attempt. A challenge creates a failure and never publishes data.

### P3: Parsers and observations

- Versioned search-result parser.
- Versioned product-page parser.
- Listing, price, offer, rating, review-count, BSR, badge, and availability observations.
- Evidence references, timestamps, freshness, confidence, and publication status.
- Golden files and idempotent reprocessing.

Proof: real or sanitized captures parse into existing contracts; duplicate processing creates no duplicate observations; malformed layouts quarantine safely.

### P4: Competitor discovery

- Discover repeated ASINs from configured keywords, bestseller pages, and related-product modules.
- Deduplicate by ASIN.
- Score category relevance, appearance frequency, rank strength, and Novel SKU similarity.
- Show candidate evidence and confidence.
- Approve, reject, archive, and correct candidates.
- Create competitor records and battle-card links only after approval.

Proof: repeated captured ASINs appear as candidates, uncertain candidates remain pending, and approval creates an active competitor without manual database edits.

### P5: Paid intelligence views

- Keyword rank and Share of Voice.
- Sponsored presence and daypart summaries where observations exist.
- Price-per-unit, offer, availability, listing, and review comparisons.
- Before/after changes.
- Scorecards with explicit unknown states.
- Deterministic gaps, actions, and alerts.
- Evidence and freshness visible beside every important value.

Proof: one Novel SKU and one approved competitor can be compared using collected evidence; missing data is unknown, not zero.

### P6: Credential activation

- Activate SP-API, Ads API, and Brand Analytics through environment variables.
- Verify permissions before scheduling.
- Store raw API responses before normalization.
- Add own orders, inventory, ads, search terms, and Brand Analytics data to the same dashboard.
- Keep competitor spend, units, and revenue estimated only when evidence gates pass.

Proof: credentials populate measured own-data panels without replacing public-data contracts; failed permission checks remain visible.

## Non-negotiable safety rules

- Official API first when available.
- Public, logged-out Amazon pages only.
- Never bypass CAPTCHA, login walls, bot detection, or access controls.
- Store raw evidence before parsing.
- Quarantine suspicious or malformed output.
- Never display estimates as measured values.
- Never expose reviewer identity.

## Release gates

- Backend lint, mypy, unit/integration tests, migration checks, and diff check pass.
- Frontend typecheck, tests, and production build pass.
- At least one real Amazon capture succeeds in an approved environment.
- Candidate discovery and approval work through the UI.
- Reprocessing is idempotent.
- PostgreSQL verification is complete.
- Vercel-to-backend CORS and access-code login are tested.
- Live, fixture-only, unavailable, stale, quarantined, and unknown capabilities are separately labelled.
