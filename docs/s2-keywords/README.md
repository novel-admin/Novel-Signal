# S2 Keyword Intelligence

## Purpose

S2 owns the approved keyword master and the configuration that links each keyword to an
owned `Product` or a `CompetitorProduct`. It stores collection cadence but does not execute
collection. S12 will create collection jobs; S3 will store organic and sponsored SERP
observations; S4 will derive advertising intelligence.

## Keyword identity and lifecycle

`keyword_text` preserves the operator's entered phrase after trimming and collapsing repeated
whitespace. `normalized_text` additionally applies Unicode-aware case normalization and is used
only for identity. An active partial unique index on `(marketplace, normalized_text)` prevents
capitalisation and whitespace duplicates. Singular/plural forms, misspellings, regional terms,
and different languages remain separate because S2 performs no semantic rewriting.

`tracking_status` is either `active` or `paused` and is independent of `archived_at`. Archiving
retires a master record without deleting it. Restore revalidates active uniqueness and dependency
rules and returns a conflict if an equivalent active record exists.

## Classification and provenance

Keywords use shared tiers `T1`, `T2`, and `T3`, and manual intent values:
`generic_category`, `attribute_long_tail`, `problem_benefit`, `own_brand`,
`competitor_brand`, `adjacent`, or `unclassified`.

One Keyword has many `KeywordSource` rows. This preserves multiple discovery sources while
deduplicating the master keyword. Source rows store only source type, an optional stable
reference, discovery timestamp, and safe metadata—not raw source payloads.

Provenance is additive. API updates merge new source identities into the existing set and never
silently discard a previously recorded source. A repeated `(source_type, source_reference)` is
rejected within one request and ignored as an addition when already stored. During CSV import, an
existing active keyword is enriched when the row supplies at least one new source; a row whose
keyword and complete source set already exist is reported as a validation error. CSV enrichment
does not overwrite the keyword's classification or estimate fields.

Nullable `volume_estimate`, `seasonality_index`, and `trend_metadata` are explicitly estimates or
metadata supplied by an approved source. `NULL` means unknown/not supplied, not zero. These values
must retain their source in `KeywordSource`; they are planning inputs, not measured actuals, and
must not be presented with false precision. Current rank, SOV, gaps, conversions, and revenue-at-
stake are not master fields; future observation/derived tables join through the Keyword UUID.

## Priority workflow

The canonical priority set is an unarchived keyword with `tier=T1` and
`tracking_status=active`. S2 deliberately does not store a second `is_priority` flag that could
drift out of sync. Operators can combine the visible tier/status filters, use bulk update to move
approved rows between tiers or statuses, or request `GET /api/v1/keywords?priority_only=true`.
That SQL-backed contract gives S12 and S3 a stable, pagination-ready priority input.

## TrackingTarget

A TrackingTarget links one active Keyword to exactly one active `Product` or
`CompetitorProduct`. A database check enforces the exclusive target rule. Two partial unique
indexes prevent duplicate active mappings. `cadence_minutes` must be positive; Week 1 uses 240
minutes (four hours). `enabled` pauses scheduling intent without archiving the configuration.

The downstream scheduling contract is: S12 reads active, unarchived priority keywords and their
active, enabled TrackingTargets; each target supplies exactly one S1 product identity and its
positive cadence. S12 owns job creation/execution. S3 consumes those jobs and stores timestamped
SERP captures keyed back to Keyword and the configured product identity. S2 never claims that a
configured target has been collected.

## API and CSV workflow

Versioned endpoints are under `/api/v1/keywords`. Lists are SQL-filtered and return
`items`, `total`, `limit`, and `offset` (`limit=50`, maximum 200). CRUD uses archive/restore—there
is no hard-delete API. Bulk update supports complete-request tier and tracking-status changes.

CSV resources support `keywords` and `tracking-targets`:

1. Download `/csv/{entity}/template`.
2. POST the complete text to `/csv/{entity}/dry-run`.
3. Review every row error; dry-run performs zero writes.
4. POST the same validated text to `/csv/{entity}/import`.
5. Import validates again and commits once; unexpected failure rolls back the complete file.
6. Download `/csv/{entity}/export`; add `include_archived=true` when required.

TrackingTarget CSV uses UUIDs for Keyword, Product, and CompetitorProduct references. Keyword
sources use a pipe-separated list of controlled source values.

All intent values are accepted consistently by create, update, list filtering, CSV import/export,
and the `/keywords` form: `generic_category`, `attribute_long_tail`, `problem_benefit`,
`own_brand`, `competitor_brand`, `adjacent`, and `unclassified`. The same is true for all nine
controlled source values. CSV import is transactional after a zero-write dry run, while API bulk
updates are complete-request operations.

## Future SOV and gap intelligence

S2 is the configuration foundation, not the observation layer. Future S3 `SerpCapture` records
need keyword ID, marketplace, captured time, query context, organic/sponsored result positions,
listing identity, seller/brand where available, and collection provenance. Share of Voice is then
derived over an explicit window and denominator from those observations; it is never stored as an
invented Keyword master value.

Keyword-gap analysis additionally depends on observed competitors/listings, coverage windows,
rank thresholds, match confidence, and a defined owned-vs-competitor comparison set. Those inputs
do not exist in Week 1, so S2 exposes identity, priority, provenance, and TrackingTarget joins only.

## Local administration

Run the API at `http://127.0.0.1:8000` and web application at `http://localhost:3000`, then open
`http://localhost:3000/keywords`. The screen uses the real FastAPI endpoints and displays an empty
state when no records exist.
