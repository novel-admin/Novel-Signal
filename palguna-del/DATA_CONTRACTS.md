# Palguna Data and Handoff Contracts

These contracts prevent duplicate implementations and unsafe assumptions.

## Ownership rule

Akanksh publishes universe, keyword, SERP, listing and price observations. Palguna consumes those published records and owns Amazon Ads, reviews, estimates, scorecards, gaps, actions and alerts.

Palguna must not parse Amazon SERP or product HTML again inside intelligence services.

## Input quality gate

An input can affect a score, gap, estimate or alert only when:

- publication status is published
- raw evidence ID exists
- parser version exists
- required identity is mapped
- observation is inside the freshness window
- quarantine reason is empty

Unknown or stale input remains unknown. It must not silently become zero.

## Amazon Ads to S2 handoff

Palguna publishes normalized search-term contributions with:

- profile ID and marketplace
- campaign and ad-group identity
- search term
- matched keyword and match type when supplied
- date window
- impressions
- clicks
- spend and currency
- orders and sales
- raw evidence ID
- parser version
- confidence `measured`

Akanksh owns canonical keyword matching and S2 source upsert. Replaying a report must not duplicate the source contribution.

## SERP to S4 handoff

Palguna consumes sponsored result rows containing:

- capture ID
- keyword ID
- capture timestamp
- geo and device
- ASIN and mapped competitor identity
- placement type and placement position
- raw evidence ID
- parser version

Competitor ad presence is measured at the sampled time. Continuous days and daypart patterns are derived.

## Reviews handoff

Akanksh's collection supplies either public review observations or product-page aggregates with evidence lineage.

Palguna publishes:

- daily rating and count observations
- review velocity
- rating trend
- topic counts and trend
- sample size and confidence

Personal reviewer data must not reach frontend responses.

## Scorecard contract

Every scorecard cell contains:

- Novel product ID
- optional competitor product ID or battle-card ID
- dimension
- score or unknown
- band
- direction and velocity
- calculation version
- calculated time
- freshness state
- confidence
- evidence references
- revenue at stake only when supported

The same formula version must be used for all SKUs in a category for a given calculation run.

## Gap contract

A gap must contain:

- deterministic fingerprint
- dimension
- entity and optional keyword
- current and benchmark values
- gap size
- root cause when known
- confidence
- evidence references
- revenue at stake or null
- status

Every Lagging scorecard cell should produce a gap or an explicit reason why no actionable gap can be created.

## Action contract

An action contains:

- originating gap or change event
- title and reason
- owner
- due date
- status
- recommended playbook entry
- outcome note
- status history
- 7/14/30-day impact records

No action should be generated without inspectable evidence.

## Alert contract

An alert contains:

- rule and alert type
- severity
- target SKU, competitor and keyword where relevant
- opened, acknowledged and resolved times
- evidence references
- linked gap/action
- deduplication fingerprint

## API compatibility rule

- Additive response fields are allowed.
- Renaming or removing shared fields requires both consumers to change in the same pull request.
- Shared migrations require review by both developers.
- Keep one Alembic head.
- Reuse existing models rather than creating alternate tables for the same concept.
