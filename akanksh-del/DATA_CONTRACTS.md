# Akanksh Data and Handoff Contracts

These contracts prevent both developers from writing competing implementations.

## Ownership rule

Akanksh owns collection and publication for universe, keywords, SERPs, listings and prices. Palguna consumes published records. Palguna owns Amazon Ads normalization, reviews, models, scorecards, gaps, actions and alerts.

Shared files should be changed only after both developers agree on the schema.

## Required lineage fields

Every normalized observation must expose:

- `source_type`
- `observed_at`
- `collected_at`
- `raw_evidence_id`
- `parser_version_id` or parser version string
- `publication_status`
- `quarantine_reason` when not published
- `confidence`: measured, derived, estimated or unknown
- `geo` and `device` when the source can vary by them

## Keyword contract

Canonical keyword identity is normalized text plus market and language where required.

Each source contribution must retain:

- source type
- source record/report date
- first and last seen time
- supplied volume or frequency rank
- clicks, impressions, CTR or conversion share when supplied
- related ASIN, campaign, page or domain
- raw evidence ID

Never overwrite one source's metric with another source's metric.

## SERP capture contract

One capture contains:

- keyword ID
- platform: `amazon_in` or `google_organic`
- query text
- captured time
- geo/pincode
- device
- success/failure status
- raw evidence ID
- parser version

Each result contains:

- absolute position
- placement position
- placement type
- ASIN for Amazon or URL/domain for Google
- mapped product/competitor identity when known
- title and brand
- price and offer fields when Amazon provides them
- rating, review count, badge and delivery fields when present
- evidence pointer

Palguna uses sponsored Amazon rows for S4. Akanksh must not separately calculate competitor ad spend.

## Listing snapshot contract

Snapshots are immutable observations. A later snapshot creates field-level changes; it does not update the old snapshot.

Required identity:

- owned `product_id` or `competitor_product_id`
- marketplace and ASIN
- observed time and geo

Required evidence:

- raw evidence ID
- parser version
- publication status
- field completeness score

## Price contract

Required fields:

- product identity
- selling price and currency
- MRP
- discount
- pack quantity and unit
- normalized price per unit when valid
- coupon and deal information
- seller/Buy Box information when visible
- availability and delivery promise
- pincode and observation time
- raw evidence and parser lineage

Palguna's scorecard must use the same latest published observation used by the comparison screen.

## Change-event contract

Akanksh publishes idempotent events for:

- rank movement across configured thresholds
- badge gained or lost
- listing field changed
- price changed
- coupon/deal started or ended
- availability changed
- new competitor result observed

Fingerprint format must be deterministic from target, event type, new observation and changed field. Reprocessing the same evidence must not create duplicate events.

## Amazon Ads handoff from Palguna

Palguna publishes Amazon Ads search terms into an agreed import service, not directly into S2 tables.

Required fields:

- profile and marketplace
- campaign and ad group identity
- search term and matched keyword
- date window
- impressions, clicks, spend, orders and sales
- raw evidence ID
- confidence `measured`

Akanksh performs canonical keyword matching and S2 source upsert.

## API compatibility rule

- Additive response fields are allowed.
- Renaming or removing fields requires both developers to update consumers in the same pull request.
- Database migrations must remain a single Alembic chain.
- Do not create a second model for an existing concept.
