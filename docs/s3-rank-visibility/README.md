# S3 Rank & Visibility

S3 stores and analyzes normalized marketplace search-result captures. Amazon.in is the
Week-1 marketplace, but capture and result identities use the shared marketplace model.
S3 never scrapes a marketplace and does not own scheduling.

## Architecture and entities

- `SerpCapture` is one keyword × marketplace × geo × device × time observation. All owned,
  competitor, and unknown results belong to this same capture.
- `SerpResult` stores absolute, within-placement, and page positions plus normalized listing
  fields. It maps to either an S1 `Product`, an S1 `CompetitorProduct`, or neither.
- `BadgeEvent` records normalized badge acquisition/loss against the previous capture in the
  same keyword, marketplace-product, geo, and device context.
- `NewEntrantEvent` records the first page-1 appearance in that same context.

S3 depends on S1 marketplace identities and S2 keywords. Its normalized POST boundary is the
future S12 integration point: S12 can supply lineage and parser metadata without importing an
unmerged collector implementation.

## Ingestion

`POST /api/v1/rank-visibility/captures` validates the keyword and complete payload, rejects a
duplicate optional `ingestion_key`, calculates or verifies within-placement positions, resolves
active S1 identities in bulk, stores unknown marketplace IDs, and emits events in one database
transaction. Duplicate absolute positions are rejected. A marketplace ID that ambiguously exists
in both S1 identity tables is retained as unmapped. Capture page/result counts are derived from
actual rows. Source job ID, parser version, and metadata preserve available lineage.

Placement types are `organic`, `sponsored_product`, `sponsored_brand`,
`sponsored_brand_video`, `sponsored_display`, and `editorial_or_deal`. Normalized badges are
`best_seller`, `amazons_choice`, `deal`, `limited_time_deal`, `new_arrival`, and `sponsored`.

## Analytics semantics

- Latest and best rank use the best absolute result per observed capture.
- Mean Absolute Rank Movement is
  `mean(abs(r[i] - r[i-1]))` over chronological capture ranks; fewer than two observations is 0.
- Top-3/Top-10 percentages use each capture's best organic within-type rank. The denominator is
  captures where the identity was observed; a sponsored-only capture remains in the denominator.
- Brand presence includes every page-1 row. Total share is brand slots / all page-1 slots; organic
  and sponsored counts are returned separately. Missing brand is reported as `Unknown`.
- A badge event compares the closest earlier result in the same geo/device context. Repeated state
  emits no event.
- A new entrant is unique per keyword, marketplace SKU, geo, and device.

The repository has a market-share estimate carrying BSR as an input, not a durable reusable BSR
observation model. S3 therefore does not expose a fake BSR-history endpoint or tab.

## API

All routes use `/api/v1/rank-visibility`:

- `GET /meta`
- `POST /captures`, `GET /captures`, `GET /captures/{id}`
- `GET /rank-history`, `GET /visibility`, `GET /brand-presence`
- `GET /badge-events`, `GET /new-entrants`

List routes use the existing `items`, `total`, `limit`, and `offset` contract. Rank endpoints
require exactly one of `product_id`, `competitor_product_id`, or `marketplace_product_id`.

## Frontend and manual QA

Open `http://localhost:3000/rank-visibility`. The sidebar opens the same route. The six tabs show
live API results or explicit empty states, and capture rows open normalized result details.

1. Start infrastructure and migrate with `alembic -c apps/backend/alembic.ini upgrade head`.
2. Start `uvicorn novel_signal.main:app --app-dir apps/backend/src` and `pnpm dev:web`.
3. Create an S2 keyword and S1 owned/competitor products with marketplace IDs.
4. POST a capture containing those two IDs, one unknown ID, organic and sponsored placements,
   badges, and a page-2 row. Use a unique `ingestion_key`.
5. Refresh S3 and verify the capture and readable result drawer.
6. POST a later capture in the same geo/device context with changed ranks, one removed/added badge,
   and a new page-1 SKU.
7. Enter the keyword and marketplace ID in Rank history and Visibility; verify MARM and Top-3/10.
8. Verify Brand presence, Badge events, and New entrants tabs.
9. Re-submit an ingestion key (409), conflicting identity filters (422), and an invalid negative
   value (422).
10. Delete only the QA captures by their recorded UUIDs in a dedicated local/test database; never
    perform broad cleanup against shared data.

Limitations: ingestion expects already normalized rows; scheduling and collection remain external.
Analytics are observation-based and do not infer positions for missing captures.
