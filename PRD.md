# Novel Signal — Week 1 Product Requirements Document

**Status:** Build-ready draft  
**Release:** Week 1 / v0.1 — Amazon Competitive Watchtower  
**Team:** Palguna (lead) and Akanksh  
**Source of truth:** `Novel_Signal_Competitive_Intelligence_Spec_v1.0.docx`, `Document.md`, and `week1.md`  
**Target:** A usable internal release by the end of Week 1

## 1. Product summary

Novel Signal is an internal competitive-intelligence product. It tracks Novel products and their direct competitors on Amazon.in, keeps the evidence behind every observation, detects important changes, and turns those changes into work that a person can own.

The complete product will be delivered over eight weeks. Week 1 establishes the smallest complete data path:

> Configure products and keywords → collect Amazon pages → retain raw evidence → parse and validate observations → show current and historical facts → detect changes → create and assign an action.

Week 1 is not a static dashboard and does not use sample data for acceptance. It must run against approved, public, logged-out Amazon.in pages.

## 2. Problem

Today, price, stock, listing, organic rank, sponsored placement, and competitor changes are spread across marketplace pages and manual reports. This creates four problems:

1. The team cannot see Novel and its competitors from the same capture.
2. Important changes may be noticed late or without proof.
3. Historical evidence is lost when a marketplace page changes.
4. Findings do not reliably become owned, trackable actions.

## 3. Week 1 goal

By the end of Week 1, an internal user can:

1. Register Novel products, competitors, competitor products, battle-card mappings, and priority keywords.
2. Run or schedule Amazon.in search captures every four hours.
3. Run or schedule product-detail captures every hour.
4. See page-1 organic and sponsored results from the same search capture.
5. See current and historical listing, price, offer, and availability facts.
6. Open the raw evidence behind a published observation.
7. See supported changes and create or assign an action.
8. See failed or challenged collections without bad data replacing the last valid result.

## 4. Users and jobs

### 4.0 Delivery ownership

The module split for the complete eight-week project is fixed as follows:

| Module | Owner | Week 1 responsibility |
| --- | --- | --- |
| S1 — Universe & Competitor Setup | Akanksh | Full Week 1 scope |
| S2 — Keyword Intelligence | Akanksh | Full Week 1 scope |
| S3 — Rank & Visibility Tracking | Akanksh | Full Week 1 scope |
| S4 — Ad Intelligence | Palguna | Only the sponsored-placement support required by Week 1 |
| S5 — Listing & Content Intelligence | Akanksh | Full Week 1 scope |
| S6 — Price, Promo & Offer Intelligence | Akanksh | Full Week 1 scope |
| S7 — Review & Voice-of-Customer | Palguna | Not part of the Week 1 release |
| S8 — Sales & Share Estimation | Palguna | Not part of the Week 1 release |
| S9 — Benchmarking Scorecard | Palguna | Not part of the Week 1 release |
| S10 — Gap & Action Engine | Palguna | Thin change-to-action flow required in Week 1 |
| S11 — Alerting & War Room | Palguna | Week 1 operations and in-app status only |
| S12 — Collection Infrastructure | Akanksh | Full Week 1 scope |

Palguna also owns shared frontend integration, architecture, authentication, deployment, CI, observability, final integration, and release acceptance. Akanksh owns the complete implementation and tests inside his assigned modules, including their API routes, database changes, jobs, collectors, parsers, validation, and module UI support.

### 4.1 Palguna — build lead

The lead owns architecture, integration, review, deployment, priorities, and release acceptance.

Main jobs:

- Configure the initial tracked universe.
- Confirm that data and evidence are trustworthy.
- Review failures and release readiness.
- Guide the second engineer and unblock module work.

### 4.2 Category or marketplace analyst

Main jobs:

- Maintain competitors and battle cards.
- Maintain priority keywords.
- Review rank, price, stock, offer, and listing changes.
- Create, assign, and close actions.

### 4.3 Engineering operator

Main jobs:

- Check collection freshness and success.
- Inspect parser failures and quarantined captures.
- Re-run safe failed jobs.
- Confirm that the last valid observation was not overwritten.

### 4.4 Ownership boundary rules

- Akanksh may change shared contracts needed by S1, S2, S3, S5, S6, or S12 only after Palguna reviews the contract.
- Palguna consumes Akanksh's published module services and APIs. He should not duplicate collectors, parsers, or module business rules in the frontend or action modules.
- Akanksh must not place action, alert, scorecard, or authentication rules inside collection modules.
- Palguna owns cross-module user journeys and makes the final call when two modules need different contract shapes.
- Every handoff includes migrations, API contracts, tests, example data, failure behavior, and a short operator note.

## 5. Week 1 scope

### 5.0 Required live data sources

Week 1 must connect to and ingest from these source groups:

1. **Amazon SP-API:** Novel-owned orders, inventory, pricing, listings, fees, and returns that the approved seller account and roles permit.
2. **Amazon Ads API:** Novel-owned campaigns, advertised products, keywords, search terms, bids, spend, impressions, clicks, conversions, and ACOS that the approved advertising profile permits.
3. **Amazon Brand Analytics reports:** Search Query Performance and available Brand Analytics reports exposed through the approved Amazon reporting interfaces. Access depends on Brand Registry, marketplace, report type, and account permissions.
4. **Google Search Console API:** Novel-owned site query, page, country, device, click, impression, CTR, and average-position data.
5. **Meta Marketing API:** Novel-owned campaign, ad set, ad, creative, spend, impression, click, and conversion data permitted by the approved Meta business and ad accounts.
6. **Meta Ad Library access:** Public competitor creative and run information when the supported public interface and jurisdiction provide it. This is separate from Novel's private Meta Marketing API data.
7. **Approved public Amazon.in collection:** Public logged-out search and product-detail pages for competitor organic rank, sponsored placement, listing, live price, offer, badge, rating, review count, and availability facts that official APIs do not provide.

CSV remains available for initial setup and recovery, but it is not the primary Week 1 data path for these integrations.

Source precedence is binding: use an official API when it provides the required fact; scrape only the missing competitor or marketplace-view fact. Every record stores its source, account or profile scope, collection time, raw-response reference, parser/normalizer version, and measured/derived status.

### 5.1 S1 — Universe and competitor setup

Week 1 includes:

- Competitor registry.
- Novel product registry.
- Competitor-product registry.
- Amazon ASIN and product URL fields.
- One category tree level sufficient for the approved products.
- Battle cards mapping each Novel product to direct competitor products.
- Comparison basis: pack size, price band, category, and use case.
- Tracking state and cadence.
- CSV import and export for initial setup.
- Manual create, read, update, archive operations.

Week 1 does not include automatic competitor discovery, approval workflows, or monthly data-driven tier reclassification.

### 5.2 S2 — Keyword intelligence

Week 1 includes:

- Approved priority keyword registry.
- Keyword source, intent, tier, status, and notes.
- Live keyword inputs from Amazon Ads, available Brand Analytics reports, and Google Search Console.
- CSV import as a fallback for approved exports.
- Keyword-to-product and keyword-to-competitor-product tracking targets.
- Duplicate normalization using trimmed, case-folded text.
- Search capture history for every active keyword.
- A simple keyword detail view showing current Novel and competitor presence.

Week 1 does not include licensed reverse-ASIN data, volume modelling, automated clustering, revenue-at-stake, or full keyword-gap calculations.

### 5.3 S3 — Rank and visibility tracking

Week 1 includes:

- Amazon.in public search-result capture.
- One approved pincode/location.
- One desktop browser profile.
- Page 1 only.
- Four-hour default cadence for active priority keywords.
- Organic and sponsored product placement detection.
- Absolute position, within-type position, ASIN, title, brand, badge, displayed price, rating, review count, and capture time where present.
- Novel and competitor products from the same capture.
- Current rank and rank history.
- First seen and last seen for sponsored placement.
- Daily sponsored presence derived from valid captures.
- Manual run-now control for one keyword.

Week 1 does not include page 2, multiple devices, multiple pincodes, BSR velocity, advanced Share of Voice, daypart inference, creative capture, or spend estimates.

### 5.4 S5 — Listing and content intelligence

Week 1 includes:

- Amazon product-detail snapshots.
- Title, bullets, description when visible, image URLs and hashes, brand, variation data when visible, rating, review count, and category/BSR when visible.
- A field-level diff against the previous valid snapshot.
- Old value, new value, detected time, and raw evidence link.
- Listing history for a tracked product.

Week 1 does not include A+ block reconstruction, rendered visual diffs, content-quality scoring, claim classification, or compliance routing.

### 5.5 S6 — Price, promo, offer, and availability intelligence

Week 1 includes:

- Selling price and currency.
- MRP when present.
- Discount amount and percentage when derivable.
- Coupon text and normalized coupon value when safely parsable.
- Price per unit when pack quantity and unit are configured.
- Basic deal label.
- Availability state: in stock, out of stock, unavailable, unknown.
- Delivery text as evidence, without promising exact delivery.
- Hourly default cadence for tracked product pages.
- Price and availability history.
- Change events for price, coupon, and availability transitions.

Week 1 does not include bank-offer normalization, Subscribe & Save modelling, Buy Box history, promo-calendar reconstruction, elasticity, SCM margin floors, or pincode comparison.

### 5.6 S12 — Collection infrastructure

Week 1 includes:

- Schedule creation and due-job dispatch.
- Idempotent job keys so the same scheduled slot is not collected twice.
- Separate search and product-detail jobs.
- Conservative platform concurrency and delay settings.
- Public logged-out access only.
- Backoff and failure recording on challenge or block.
- No CAPTCHA solving or evasion.
- Raw response saved before parsing.
- Content hash and capture metadata.
- Versioned parser identity on every published observation.
- Schema validation before publication.
- Quarantine for invalid or suspicious parser output.
- Retry limits and a dead-letter state.
- Freshness and capture-success status.
- Golden HTML fixtures for parser tests.

### 5.7 Thin support required outside the six assigned modules

`week1.md` requires change events and actions. Week 1 therefore needs a small slice of S10:

- A supported change creates one deduplicated change event.
- A user can create an action from a change.
- An action has title, reason, owner, due date, status, and evidence link.
- Status values are `open`, `in_progress`, `done`, and `dismissed`.
- A closed action records an outcome note.

This is not the final gap engine, scorecard, alert system, or impact model.

## 6. Reduced integration surface

Week 1 deliberately reduces external dependencies while preserving the final data model and evidence path.

| Area | Week 1 boundary | Later weeks |
| --- | --- | --- |
| Marketplace | Amazon.in only | Flipkart and remaining platforms |
| Marketplace | Amazon.in only | Other marketplaces |
| Amazon-owned data | SP-API, Ads API, and permitted Brand Analytics reports | Additional Amazon programmes and regions |
| Search data | Google Search Console for Novel-owned properties | Keyword Planner and other Google products |
| Social ads | Meta Marketing API and supported Ad Library access | Other social platforms |
| Competitor data | Public logged-out Amazon.in pages | Other marketplaces and licensed sources |
| Geography | One approved pincode/location | Multiple cities and pincodes |
| Device | Desktop only | Mobile and other profiles |
| Input | Live APIs, approved public collection, admin forms, and CSV fallback | BOS/SCM and licensed data feeds |
| Auth | One internal admin role or deployment access gate | Shared BOS authentication and roles |
| Notifications | In-app event and action inbox | Email, Slack, Teams, and BOS notifications |
| Storage | PostgreSQL plus S3-compatible object storage | Managed AWS services and lifecycle policies |
| Queue | Redis-backed Celery locally and in first deployment | SQS/EventBridge adapter when scale requires it |
| SCM | No direct integration; optional CSV fields only | Live margin, stock, and cost integration |
| Intelligence | Deterministic rules | SOV, gaps, scoring, models, and confidence bands |

The reduced surface must not change core identifiers or observation schemas. Later integrations should plug into ports/adapters rather than require a data rewrite.

## 7. Core user journeys

### Journey A — Configure the market

1. User imports or creates Novel products.
2. User creates competitors and competitor products.
3. User links 3–8 relevant competitor products to a Novel product in a battle card.
4. User imports or creates priority keywords.
5. User links keywords and products as tracking targets.
6. User activates schedules.

Success: the system can show the exact products, keywords, location, and cadence it will collect.

### Journey B — Inspect a search capture

1. Scheduler creates due API-sync and public-search jobs.
2. Collector opens the approved Amazon.in search page.
3. Raw HTML and capture metadata are stored.
4. The versioned parser extracts result rows.
5. Validation either publishes all valid rows or quarantines the capture.
6. User opens a keyword and sees organic and sponsored positions.
7. User opens the raw evidence for the capture.

Success: Novel and competitor positions are comparable because they came from the same capture.

### Journey C — Inspect a product change

1. Scheduler creates a product-detail job.
2. Collector stores the raw response.
3. Parser publishes listing, price, offer, and availability observations.
4. Change detection compares them with the previous valid observation.
5. User sees the old and new values and the evidence.
6. User creates and assigns an action.

Success: an invalid capture cannot create a false change or overwrite the current valid value.

### Journey D — Handle collection failure

1. Amazon returns a challenge, block, incomplete page, timeout, or changed layout.
2. Collector stops safely and records the reason.
3. Raw evidence is retained when permitted and useful.
4. Job retries only within configured limits.
5. Invalid parser output is quarantined.
6. Operator sees the failure in the operations view.

Success: the last known valid observation remains active and the failure is visible.

## 8. Required screens

1. **Overview:** freshness, success rate, recent changes, open actions, and current job health.
2. **Universe:** competitors, Novel products, competitor products, battle cards, and CSV import/export.
3. **Keywords:** keyword list, tracking status, cadence, current positions, and run-now control.
4. **Keyword detail:** latest page-1 result set, organic/sponsored labels, history, and evidence.
5. **Product detail:** current listing, price, offer, availability, change history, and evidence.
6. **Changes:** filterable list of price, availability, listing, rank, and sponsored-placement changes.
7. **Actions:** open/assigned/completed work with evidence links.
8. **Operations:** scheduled jobs, failures, quarantine, parser version, freshness, and retries.

Responsive mobile layout is desirable but desktop is the Week 1 acceptance surface.

## 9. Functional rules

### 9.1 Evidence rules

- Store raw content before starting the parser.
- Every published observation references a capture and parser version.
- Raw content is immutable; corrections create new parser outputs.
- An evidence view shows capture time, source URL, location, device, content hash, parser version, and publication state.

### 9.2 Publication rules

- Only a successfully collected and validated capture may become `published`.
- A failed validation changes the capture to `quarantined`.
- Quarantined data is excluded from current-value and history APIs by default.
- A newer failed capture never replaces an older valid current value.
- A capture publishes atomically: either its intended observation set is accepted, or none of it is.

### 9.3 Change rules

- Compare only two consecutive valid observations for the same entity, source, geo, and device.
- No event is created for the first valid observation.
- Price changes use normalized currency minor units.
- Availability events require a state transition.
- Listing diffs use normalized text and ordered image hashes.
- Rank changes compare the same keyword and product.
- Sponsored placement changes support appeared, disappeared, and position changed.
- Event fingerprints prevent duplicates when processing is retried.

### 9.4 Measurement labels

- Values directly observed on the page are `measured`.
- Daily sponsored presence and calculated discount are `derived`.
- Week 1 does not publish estimated competitor bid, spend, budget, sales, or revenue.

## 10. Data inputs required before build acceptance

The business must supply:

- Approved Amazon.in pincode/location.
- Initial Novel product list with ASIN, name, category, pack quantity, and unit.
- Competitor list.
- Direct competitor ASINs and battle-card mapping.
- Priority keyword list and source.
- Action owner names or emails.
- Legal approval for the exact public-page collection scope.
- Amazon Login with Amazon application credentials, seller/advertising account authorization, marketplace IDs, region, and required roles.
- Google Cloud OAuth or service-account credentials plus access to the approved Search Console properties.
- Meta application credentials, long-lived system-user or approved user token, business/ad account IDs, and required permissions.
- Decision on which Meta Ad Library interface is approved and available for the target geography.

The application must provide CSV templates if these inputs are not ready on Day 1.

## 11. Success measures for Week 1

| Measure | Week 1 target |
| --- | --- |
| Configured keyword has a valid search capture | Yes |
| Search cadence | Every 4 hours |
| Product-detail cadence | Every hour |
| Organic and sponsored rows retained | Yes |
| Raw evidence linked to every observation | 100% |
| Invalid parser output reaches current views | 0 |
| Supported change creates one event | Yes |
| Change can create an owned action | Yes |
| Failed/challenged collection is visible | Yes |
| Relation-level schema and migration tests pass | Yes |

The final-product target of at least 98% capture success for two straight weeks cannot be proven inside a one-week build. Week 1 must calculate and display the metric so it can be measured from launch.

## 12. Non-functional requirements

### Security

- No marketplace credentials are used for collection.
- Secrets are supplied through environment variables or a secret manager.
- Raw evidence is not public.
- Admin mutation endpoints require an internal access control.
- Logs must not include cookies, authorization headers, or full raw pages.

### Reliability

- Jobs are idempotent.
- Network retries use capped exponential backoff with jitter.
- Challenge detection stops collection.
- Database writes for publication are transactional.
- Workers can restart without losing scheduled work.

### Performance

- Current-value API response target: under 500 ms at the Week 1 data size.
- History API response target: under 2 seconds for 30 days.
- List APIs are paginated.
- Raw bodies are read from object storage only on demand.

### Auditability

- Master-data mutations store actor and time.
- Collection state transitions are recorded.
- Actions keep status history.
- Parser version and raw evidence can be traced from every fact.

## 13. Out of scope for Week 1

- Flipkart, Meesho, quick commerce, or other marketplace collection.
- Google Ads API, Google Ads Transparency Center automation, GA4, Shopify, or other social-platform integrations unless separately approved.
- Direct BOS or SCM integration.
- Multiple geo or device profiles.
- CAPTCHA solving, account login, or block bypass.
- Advanced SOV, revenue-at-stake, automated gaps, scorecards, and war-room alerts.
- Review NLP, sales/share models, ad-spend estimates, and machine learning.
- Full A+ rendering, creative archive, visual image classification, or compliance workflow.
- Backfilled historical data unless an approved licensed source is added.

## 14. Release acceptance

Week 1 is accepted only when the following demo runs with approved live Amazon.in targets:

1. Import a small approved universe and keyword set.
2. Run one search capture and one product-detail capture.
3. Show immutable raw evidence and capture metadata.
4. Show published organic, sponsored, listing, price, and availability data.
5. Run the next capture and show a supported change when test fixtures or a real change provide one.
6. Create, assign, and close an action from that change.
7. Run a seeded broken parser fixture and show that the capture is quarantined.
8. Show that the last valid value remains current.
9. Show migrations, ER diagram, automated tests, and an operator runbook.

## 15. Open decisions

These are not silently assumed as final business facts:

| Decision | Needed by | Safe build default |
| --- | --- | --- |
| Approved pincode/location | Day 1 | Configuration placeholder; no production schedule |
| Exact Week 1 products and keywords | Day 1 | Seed with fixtures only |
| Legal approval | Before live scheduled collection | Manual runs in development only |
| Internal auth approach | Day 2 | Single admin access gate |
| Production cloud account and region | Day 2 | Docker Compose locally; AWS-ready adapters |
| Object-store bucket and retention | Day 2 | Private S3-compatible bucket, 90-day raw retention marker |
| Alert/change thresholds | Day 3 | Exact state changes only; no guessed business threshold |
| Action owners | Day 4 | Local user records |

## 16. Eight-week relationship

Week 1 builds the stable base that later weeks extend. Later releases add more sources, geographies, modules, calculations, actions, and operating controls. Week 1 schemas use platform, geo, device, capture, parser version, and confidence fields now so those additions do not require rebuilding the evidence chain.
