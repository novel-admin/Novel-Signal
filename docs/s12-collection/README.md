# S12 — Collection Infrastructure

S12 owns collection orchestration and evidence safety. It does not own S3/S5/S6 business
observations; those modules consume the evidence and execution contracts exposed here.

## Phase 1 — domain foundation

Implemented:

- idempotent `CollectionJob`
- attempt and failure audit records
- immutable raw-evidence metadata
- parser-version registry
- quarantine records
- data-quality checks

## Phase 2 — execution engine

Implemented:

- deterministic cadence-slot and idempotency-key generation
- S2 tracking-target → Amazon.in SERP job planning
- one SERP capture per keyword even when several targets share it
- hourly Amazon.in product-detail planning for active owned and competitor products
- duplicate-safe job creation backed by the Phase-1 unique idempotency constraint
- transactional attempt claiming and duplicate-delivery suppression
- pending → running → succeeded/failed lifecycle
- retryable failure audit with exponential backoff + jitter
- challenge failures represented explicitly; challenge handling is backoff/report, never bypass
- maximum-attempt terminal failure state
- executor registry for Phase-3 collector/evidence pipeline integration
- Database-backed collection planning, claiming, retry scheduling, and Render Cron execution
- collection job list/get/plan/manual-dispatch API endpoints

## Week-1 scheduling contract

- SERP cadence comes from enabled, unarchived S2 `TrackingTarget` rows. When several targets
  share a keyword, the shortest cadence wins and one keyword capture is produced per slot.
- Product-detail collection is hourly for active Amazon.in products in the Week-1 MVP.
- Idempotency keys contain platform, job type, subject identity and UTC cadence slot.
- Re-running the planner for a slot returns the existing job instead of creating duplicate work.

## Worker contract

Run collection work from the bounded Render Cron command (`python -m novel_signal.cli collect-due`).
Amazon.in concurrency is configured separately from application code and should respect `amazon_in_concurrency`; the collector layer is also
responsible for configured politeness delays. Phase 3 will register concrete executors for SERP
and product-detail capture.

A challenge or block must be raised as a `CollectionExecutionError` with failure type
`challenge`; the lifecycle records it, backs off if attempts remain, and never attempts to solve
or bypass the challenge.

## Phase 3 — evidence, parser and quarantine gate

Implemented:

- immutable SHA-256-addressed raw-object storage with gzip compression
- raw-evidence DB durability boundary before any parser runs
- parser registry keyed by platform + page type
- persisted parser-version registration
- generic schema/completeness validation with required-field fill-rate checks
- data-quality records for field-fill rate, row count and parser consistency failures
- challenge handling after raw preservation and before parsing
- parser exceptions quarantined with retained raw evidence
- validation failures quarantined with row-level schema errors and parsed payload
- normalized publisher contract used only after validation succeeds
- Direct execution support for a `quarantined` terminal state
- read APIs for raw evidence, quarantine records and data-quality checks

The generic publisher contract intentionally does not create S3/S5/S6 observation tables. Those
modules own their normalized observation schemas and plug a publisher into this S12 gate.
