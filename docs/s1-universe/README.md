# S1 Universe and competitor setup

## Purpose

S1 is the master-data foundation for Novel Signal. It records owned products, competitors,
competitor marketplace listings, and the battle cards that define direct comparisons. It does not
collect marketplace observations or prices.

## Domain model

- **Competitor** — competitor brand, parent company, Week 1 Amazon setup, positioning, threat and
  analyst ownership.
- **Product** — an owned product identified by a unique internal SKU and optional marketplace ID.
- **CompetitorProduct** — a competitor's marketplace listing.
- **BattleCard** — an owned product's named comparison configuration.
- **BattleCardItem** — a competitor product attached to a battle card with priority and comparison
  basis flags.

Relationships and important constraints are shown in [the ER diagram](./er-diagram.md).

## Identity and lifecycle rules

Week 1 supports `amazon_in`. An Amazon marketplace product ID is normalized to uppercase and must
be exactly ten alphanumeric characters. Tracking tiers are `T1`, `T2`, and `T3`; they represent the
configured monitoring priority, not collected observations.

Records are never hard deleted. Archive sets `archived_at`; restore clears it after checking active
name, SKU, marketplace identity and battle-card mapping conflicts. Active list endpoints exclude
archived rows unless `include_archived=true` is supplied. Archived rows remain retrievable by ID.

Within `CompetitorProduct`, `(marketplace, marketplace_product_id)` identifies one active listing
across all competitors. Archiving releases that identity for reuse; restoring rechecks ownership
and returns a conflict when another active competitor product now uses it. Owned `Product`
identities use the same marketplace rule independently within the Product table; S1 intentionally
does not create cross-table uniqueness.

## API

The five resources live below `/api/v1/universe`:

- `/competitors`
- `/products`
- `/competitor-products`
- `/battle-cards`
- `/battle-card-items`

Each supports list, create, get by ID, update, archive and restore. Lists use `limit` (default 50,
maximum 200) and `offset`, return a stable `{items,total,limit,offset}` envelope, and expose the
Week 1 filters documented in OpenAPI at `http://127.0.0.1:8000/docs`.

Example competitor creation:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/universe/competitors \
  -H 'Content-Type: application/json' \
  -d '{"name":"Example Competitor","positioning_tier":"mid","threat_rating":3}'
```

Example product creation:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/universe/products \
  -H 'Content-Type: application/json' \
  -d '{"internal_sku":"EXAMPLE-001","name":"Example Product","brand":"Example Brand","category":"Baby Care","marketplace":"amazon_in","marketplace_product_id":"B0EXAMPLE1","tracking_tier":"T1"}'
```

## First setup workflow

1. Create a competitor with its Amazon store/seller configuration.
2. Create an owned product using its internal SKU.
3. Create a competitor product and select the competitor.
4. Create a battle card and select the owned product.
5. Add competitor products as battle-card items. Set priority and only the comparison-basis flags
   supported by the configuration evidence.
6. Edit, archive, show archived and restore through `/universe` or the API.

## CSV workflow

CSV endpoints are scoped by entity:

- `GET /csv/{entity}/template`
- `POST /csv/{entity}/dry-run`
- `POST /csv/{entity}/import`
- `GET /csv/{entity}/export`

Valid entities are `competitors`, `products`, `competitor-products`, `battle-cards`, and
`battle-card-items`. Templates contain stable business-facing headers and one clearly labelled
sample row. Internal UUIDs are not required:

- Competitor products resolve `competitor_name`.
- Battle cards resolve `product_internal_sku`.
- Battle-card items resolve a battle card through `battle_card_product_internal_sku` plus
  `battle_card_name`, and resolve a competitor product through `competitor_marketplace` plus
  `competitor_marketplace_product_id`.

Missing references produce row-specific errors. A battle-card name that is not unique for its
owned product is treated as ambiguous and fails safely. Exports use these same readable references.

Dry-run parses every row, performs Pydantic and domain validation, checks in-file duplicates,
foreign keys and database conflicts, and writes zero rows. The response includes total, valid and
invalid row counts plus row/field/code/message errors.

Import repeats full validation. Any invalid row rejects the whole file. A valid file is inserted in
one transaction; unexpected errors roll the transaction back. Export includes active rows by
default and accepts `include_archived=true`.

In the frontend, choose the relevant Universe tab, download its template, select a completed CSV,
run the dry-run, review errors, and confirm only when validation passes. Imported rows are reloaded
from FastAPI immediately.

## Local verification

1. Start PostgreSQL, Redis and MinIO using the repository Compose file.
2. Activate `.venv` and start FastAPI without broad project-root reload:
   `uvicorn novel_signal.main:app --app-dir apps/backend/src`.
3. Start the web application with `pnpm dev:web`.
4. Open `http://localhost:3000/universe` and perform the normal and CSV workflows above.
5. Refresh the page and verify the records remain, confirming PostgreSQL persistence.
