# Palguna Detailed Implementation Plan

Palguna should build one complete intelligence path before expanding calculations:

`published observation -> metric -> scorecard -> gap -> action -> alert -> dashboard`

## P1. Complete Amazon Ads ingestion

Own `apps/backend/src/novel_signal/sources/amazon/ads_api.py` and the S4 normalization path.

Required Week 1 data:

- campaigns and ad groups
- advertised products
- targeting keywords
- customer search terms
- impressions, clicks, spend, orders and sales
- CTR, CPC, conversion rate, ACOS and ROAS derived from measured inputs
- date, profile, marketplace and campaign identity

Tasks:

1. Verify the current Amazon Ads API resources and reporting workflow against the account's approved region and API version.
2. Use the correct profile scope header for profile-specific requests.
3. Implement asynchronous report creation, status polling and document download where the API requires reports.
4. Return raw pages/documents without normalization inside the client.
5. Save every raw response through S12 before parsing.
6. Add versioned parsers and normalized own-ad performance records.
7. Publish search terms through the handoff contract in `DATA_CONTRACTS.md` for Akanksh's S2 upsert.
8. Make retries idempotent by report identity, profile and date window.
9. Expose actual connection and last-sync status.

Do not log access tokens or report download URLs.

## P2. Complete competitor ad intelligence

Competitor Amazon ad presence comes from sponsored rows in Akanksh's Amazon SERP captures.

Tasks:

1. Consume only published SERP result rows.
2. Create idempotent competitor ad observations by capture, keyword, ASIN and slot.
3. Calculate first seen, last seen, continuous ad-presence days and total ad days.
4. Calculate keyword ad breadth, sponsored slot share and average sponsored position.
5. Build hour-by-day daypart profiles.
6. Mark budget-exhaustion behaviour as an inference, never a measured fact.
7. Compare competitor observed presence with Novel's measured Amazon Ads efficiency.
8. Add S4 APIs and a frontend screen with underlying evidence.

For Week 1, defer competitor spend estimates unless search-volume and CPC calibration inputs are sufficient. An absent estimate is better than a false number.

## P3. Complete review intelligence

Akanksh publishes public Amazon review/rating observations or product-page review aggregates. Palguna owns the intelligence derived from them.

Tasks:

1. Require raw evidence and publication status for all inputs.
2. Calculate review count change and review velocity by SKU and day.
3. Calculate rating trajectory and identify material drops.
4. Use a clear category taxonomy for complaint and praise themes.
5. Store topic counts, sentiment direction and sample size.
6. Hash any public reviewer identity before storage; do not expose it in product APIs.
7. Build comparison APIs for Novel SKU versus battle-card competitors.
8. Add a review intelligence screen with rating, velocity, topic and evidence views.

Use deterministic keyword/topic rules for V1 unless a model is already approved and available. Do not block the release on an external NLP service.

## P4. Build practical S8 estimates

The full specification describes a long-running calibration model. Week 1 needs an honest first version.

Tasks:

1. Use Novel first-party sales or order aggregates only where SP-API permissions supply them.
2. Join Novel BSR and review velocity with the same time windows.
3. Fit a simple, inspectable category model only when there are enough observations.
4. Store model version, training window, sample size and error.
5. Produce competitor unit ranges and market-share ranges, not exact values.
6. Set confidence from sample size, freshness and backtest error.
7. Refuse estimation when minimum evidence is not met.
8. Build a small market-share view showing model status and assumptions.

The product must clearly separate measured Novel values from estimated competitor values.

## P5. Compute S9 scorecards

Required Week 1 dimensions per Novel SKU and battle-card competitor:

- Amazon organic visibility
- Amazon paid presence
- Google organic visibility
- Price competitiveness
- Listing/content quality
- Social proof from ratings and reviews
- Availability

Tasks:

1. Define a 0-100 formula for each dimension using named inputs.
2. Normalize within the relevant category and battle card.
3. Store formula version and evidence references.
4. Mark a cell unknown when a required input is absent or stale.
5. Calculate Leading, At Par and Lagging bands from explicit thresholds.
6. Retain score history.
7. Build SKU, competitor and category views.
8. Add freshness and confidence indicators to every cell.

Do not average unknown values as zero. Do not show a total score without stating which dimensions are unavailable.

## P6. Automate S10 gaps and actions

Use the existing actions models and APIs.

Generate gaps for:

- organic keyword visibility
- sponsored keyword presence
- keyword coverage
- price-per-unit disadvantage
- listing-content weakness
- rating/review weakness
- availability loss

Tasks:

1. Generate deterministic gap fingerprints.
2. Link each gap to scorecard cells and source evidence.
3. Classify a simple root cause from known inputs.
4. Rank by business priority, gap size and available demand signal.
5. Use revenue-at-stake only when its inputs are available; otherwise show priority without a fake rupee value.
6. Generate recommended actions from a small versioned playbook.
7. Require owner and due date before an action becomes active.
8. Schedule 7/14/30-day impact measurements.
9. Prevent duplicate open actions for the same gap.

## P7. Implement S11 alerts and war room

Create focused alert models, service, APIs and frontend.

Required alert types:

- Novel SKU loses top-10 rank
- competitor enters top results
- competitor starts sponsored presence on a T1 keyword
- Novel or competitor price changes materially
- competitor becomes unavailable
- important listing field changes
- rating drops materially
- collection freshness or completeness breaches SLA

Tasks:

1. Store alert rule, alert event, severity, evidence, status and timestamps.
2. Deduplicate alerts while the same condition remains active.
3. Support open, acknowledged and resolved states.
4. Link alerts to the relevant SKU, competitor, keyword and action.
5. Build an in-product war-room view ordered by severity and recency.
6. Keep external email/Slack/WhatsApp delivery out unless already available without new infrastructure.

## P8. Build the main product experience

Replace the static overview at `apps/web/app/page.tsx`.

The overview must answer:

- How many Novel SKUs are tracked and fresh?
- Which SKUs are leading or lagging?
- Where did rankings move?
- Which competitor price or listing changes matter?
- Where are keyword gaps?
- Which alerts and actions need attention today?

Add or complete routes for:

- `/ads`
- `/reviews`
- `/market-share`
- `/scorecards`
- `/alerts`
- existing `/changes`, `/actions` and `/operations`

Use the existing Next.js and API patterns. Do not introduce a new state-management or component framework this week.

## P9. Release integration

Tasks:

1. Review shared migrations before merge and keep one Alembic head.
2. Ensure all dashboards read published observations only.
3. Add API and UI error states for stale, missing and quarantined data.
4. Run the complete acceptance dataset through both developers' modules.
5. Produce a release checklist showing live, fixture-only and unavailable capabilities separately.
6. Fix release blockers; defer advanced modelling polish.
