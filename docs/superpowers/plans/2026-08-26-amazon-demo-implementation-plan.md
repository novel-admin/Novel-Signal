# Amazon demo implementation plan

## Outcome

Make the Amazon-only demo useful with real public data now, then expand the same workflow when Amazon API credentials arrive.

## Work packages

### 1. Deployment and access foundation

- Use `CORS_ORIGINS` instead of a hard-coded origin.
- Keep `NEXT_PUBLIC_API_URL` pointing to the backend `/api/v1` prefix.
- Add demo access-code authentication with an HTTP-only signed cookie.
- Protect backend API routes while leaving health and login/session endpoints public.
- Add CORS and authentication tests.

### 2. Novel SKU onboarding

- Let the user create or import Novel SKUs with Amazon ASIN, category, pack size, and tracking tier.
- Validate Amazon.in identity and prevent duplicate ASINs.
- Generate seed keywords from configured terms, product title, category, and approved suggestions.
- Show readiness before collection starts.

### 3. Amazon public collection

- Add allowlisted Amazon.in search, product, bestseller, and related-product capture requests.
- Support desktop/mobile profiles and configured pincodes.
- Use plain HTTP where sufficient and Playwright only for JS-rendered pages.
- Store immutable compressed HTML and screenshots before parsing.
- Record attempts, retries, response status, challenge type, and terminal failure.
- Keep collection disabled until legal/location approval is recorded.

### 4. Versioned parsing and publication

- Build parsers for search results, product pages, listing fields, price/offers, ratings/reviews, BSR, badges, and availability.
- Add golden files for normal, missing-field, changed-layout, duplicate, malformed, and challenged pages.
- Quarantine suspicious field-fill drops and malformed output.
- Publish only records with raw evidence, parser version, timestamps, identity, freshness, and confidence.
- Make repeated processing idempotent.

### 5. Automatic competitor discovery

- Run weekly discovery over T1 keywords, bestseller pages, and related-product modules.
- Deduplicate by ASIN and brand.
- Score candidates from repeated appearance, rank strength, category match, and Novel SKU overlap.
- Display source captures, first/last seen, confidence, and proposed mapping.
- Support approve, reject, archive, and manual correction.
- Create active competitor products and battle-card items only after approval.

### 6. Amazon intelligence

- Calculate organic rank, top-3/top-10 presence, SOV, sponsored presence, price-per-unit, offer history, availability, listing completeness, rating movement, review velocity, BSR trend, and change events.
- Use same-capture results for Novel-versus-competitor comparisons.
- Keep competitor sales, spend, and revenue as unknown until a guarded model has sufficient evidence.
- Generate scorecard cells, gaps, actions, and alerts only from published fresh observations.

### 7. Complete dashboard

- Overview: tracked SKUs, freshness, leading/lagging dimensions, recent changes, gaps, actions, and alerts.
- SKU battle card: Novel product beside approved competitors.
- Keyword view: rank, SOV, sponsored presence, and movement.
- Competitor discovery queue: candidates and evidence.
- Listing/price/review views: measured values and change history.
- Collection health: attempts, successes, failures, quarantine, freshness, and completeness.
- Explicit loading, empty, stale, quarantined, partial, error, measured, estimated, and unknown states.

### 8. Credential activation

- Add environment variables for SP-API, Ads API, and Brand Analytics.
- Verify credentials and permissions before scheduling syncs.
- Store raw API responses before normalization.
- Add own-performance and search-term ingestion without changing public observation contracts.
- Show connection and last-sync status in Operations.

## Acceptance checks

- A configured Novel SKU can produce a real Amazon search capture.
- A product-page capture produces inspectable raw evidence and published fields.
- Reprocessing the same capture creates no duplicates.
- A repeated competitor appears in the discovery queue with evidence.
- Approval creates a competitor product and battle-card mapping.
- Missing or challenged captures never become zero values.
- The dashboard works with public data and shows unknown states for credential-dependent metrics.
- A real Amazon credential run later populates the same dashboard without schema replacement.
- CORS works from the configured Vercel origin.
- The demo access code blocks unauthenticated API and dashboard access.

## Explicit non-goals

- Unrestricted internet search.
- Login-only Amazon pages.
- CAPTCHA or bot-detection bypass.
- Exact competitor spend, units, or revenue without validated models.
- Calling fixture data live.
- Automatic activation of uncertain competitor matches.
