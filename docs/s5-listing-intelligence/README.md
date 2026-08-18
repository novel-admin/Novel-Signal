# S5 Listing Intelligence

S5 stores normalized marketplace product-detail snapshots for owned S1 Products,
CompetitorProducts, and unmapped marketplace identities. It performs no network collection. S12
connects through `source_job_id`; raw HTML and binary evidence remain in S12.

## Architecture and snapshot

`ListingSnapshot` contains the marketplace identity, optional exclusive S1 mapping, capture
context, S12 job lineage, parser/source information, normalized title, brand, category path,
bullets, key features, description, A+ sections, image URLs/hashes, video and variation fields,
generic metadata, and a durable deterministic completeness result. `ListingChangeEvent` stores
field-level old/new JSON values linked to current and previous snapshots.

Ingestion trims surrounding whitespace, collapses repeated text whitespace, preserves punctuation
and bullet order, removes exact duplicate list values, and uses hashes before URLs as image
identity. It downloads nothing. The first snapshot is a quiet baseline. Later snapshots compare
the same mapped product, competitor product, or marketplace identity before the capture time.
Changes are `added`, `removed`, or `modified`. Images additionally emit `image_added`,
`image_removed`, and ordered `main_image` changes; normal `image_count` is also tracked.

## Completeness formula

- Title: 15
- Brand: 5
- At least three bullets: 20
- Description: 10
- A+ present: 15
- At least five images: 20
- Video present: 5
- Variation information: 10

Total is exactly 0–100. APIs return the component breakdown plus achieved and missing components.
Quality stats are title length, bullet count/characters available from content, description length,
image count, A+, video, variations, and completeness—no opaque SEO or AI score.

## Comparison gaps

The latest owned and competitor snapshots produce raw metric deltas and only these deterministic
labels: `owned_missing_a_plus`, `owned_has_fewer_images`, `owned_has_fewer_bullets`,
`owned_missing_video`, and `owned_lower_completeness`.

## API and UI

Under `/api/v1/listing-intelligence`: `meta`, POST/list/detail `snapshots`, `latest`, `history`,
`changes`, `comparison`, and `completeness`. Identity analytics require exactly one of
`product_id`, `competitor_product_id`, or `marketplace_product_id`. Lists use the shared
items/total/limit/offset contract.

Open `http://localhost:3000/listing-intelligence`. Tabs are Snapshots, History, Changes,
Completeness, and Comparison. They use live APIs and explicit empty/error/loading states.

## Manual QA

1. Start infrastructure, migrate, then start FastAPI and Next.js.
2. Create one owned and one competitor S1 product with distinct marketplace IDs.
3. POST baseline snapshots for both IDs with unique ingestion keys; verify the UI and scores.
4. POST a later owned snapshot changing title/bullets, adding and removing an image, changing A+,
   video, and variations. Confirm the change timeline and latest/history views.
5. Post the same normalized values with different surrounding/repeated whitespace; confirm no text
   event.
6. Post a later competitor snapshot and verify comparison deltas/gaps update.
7. Verify image URL/hash changes, completeness breakdown, a negative-count 422, duplicate-key 409,
   and conflicting-identity 422.
8. Exercise all five UI tabs and capture detail.
9. In a dedicated local QA database, delete change rows then snapshot rows by the exact QA UUIDs;
   never broadly delete S1, S12, or unrelated records.

Limitations: S5 expects normalized input and does not collect, download, OCR, generate copy, or
infer semantic listing quality. Unmapped marketplace IDs are retained consistently with S3.
