# Palguna Intelligence Delivery Design

Date: 25 August 2026
Owner: Palguna

## Goal

Complete the Palguna-owned Novel Signal path for Amazon.in:

`raw evidence -> versioned parser -> published observation -> metric -> scorecard -> gap -> action -> alert -> UI`

The work covers S4, S7, S8, S9, S10, S11, Amazon Ads ingestion, the main overview, and release verification.

## Scope

- Complete Amazon Ads report ingestion and raw evidence storage.
- Derive competitor ad intelligence from published sponsored SERP observations.
- Calculate evidence-backed review intelligence.
- Produce guarded unit and market-share ranges when evidence is sufficient.
- Calculate versioned scorecards with explicit unknown states.
- Generate deterministic gaps, recommended actions, and impact schedules.
- Persist and deduplicate alerts and expose a war-room workflow.
- Add overview, ads, reviews, market-share, scorecard, and alert screens.
- Preserve existing S1, S2, S3, S5, S6, and S12 ownership boundaries.

Meta, Google Ads Transparency Center, BOS/SCM integration, shared authentication, and unsupported competitor spend estimates remain excluded.

## Architecture

### Evidence boundary

All intelligence input passes one shared quality gate. An observation is usable only when it is published, has raw evidence and parser lineage, is not quarantined, has a mapped identity, and is fresh for the calculation.

Rejected input returns an explicit reason. It never becomes zero and never reaches metrics, scorecards, gaps, actions, or alerts.

### Amazon Ads

The client remains raw-first. It verifies profiles, applies profile scope headers, creates asynchronous reports, polls with bounded backoff, downloads completed documents, and returns raw payloads. S12 stores payloads before a versioned parser creates measured own-ad performance and search-term handoff records.

Idempotency uses source, profile, report type, date window, and report identity. Secrets and document URLs are never logged or returned to product APIs.

### Intelligence modules

- S4 derives sampled sponsored presence, daily continuity, keyword breadth, sponsored share, average position, and daypart profiles.
- S7 derives rating movement, review-count changes, velocity, deterministic topics, sample size, and confidence.
- S8 accepts only evidence-backed model fits and returns ranges. It refuses estimates below the minimum evidence gate.
- S9 calculates named, versioned dimensions. A cell may contain a score or an explicit unknown reason.
- S10 creates deterministic gaps from lagging cells, chooses versioned playbook recommendations, links actions to gaps, and schedules 7/14/30-day impact checks.
- S11 evaluates versioned rules, deduplicates active conditions, and supports open, acknowledged, and resolved states.

### Product API and UI

Routers perform validation and HTTP mapping. Services own rules. Repositories own persistence.

The UI adds `/ads`, `/reviews`, `/market-share`, `/scorecards`, and `/alerts`, and replaces the static overview. Every important value shows confidence, freshness, source, and an evidence path. Loading, empty, stale, quarantined, partial, and error states are explicit.

## Data changes

Use additive migrations with one Alembic head. Extend existing tables instead of creating duplicate concepts.

Required additions include:

- complete lineage and freshness fields on intelligence inputs and outputs;
- nullable score plus unknown reason, formula version, and calculated time on scorecards;
- gap linkage, playbook linkage, and activation rules on actions;
- persisted alert rules and events;
- Amazon Ads report and search-term handoff identities where existing S12 records are not sufficient.

## Error handling

- Expected source failures map to clear permission, rate-limit, timeout, malformed-response, empty-response, failed-report, and expired-report errors.
- Retries use bounded backoff and do not duplicate evidence or normalized outputs.
- Missing evidence produces an unknown or refusal result.
- A failed optional live check does not make fixture-backed capability live.

## Testing

- Unit tests cover every formula, quality gate, transition, fingerprint, and refusal path.
- Mocked transport tests cover Amazon Ads reports and failures.
- Integration tests cover raw storage through published intelligence and duplicate processing.
- Frontend tests cover live, partial, empty, stale, quarantined, error, and action/alert workflows.
- PostgreSQL migration verification and one Alembic head are release gates.
- Live Amazon tests are opt-in and only reported as verified when credentials succeed.

## Delivery order

1. Shared evidence gate and additive schema corrections.
2. Scorecard, gap, action, and alert vertical slice.
3. Amazon Ads raw report ingestion and S4 normalization.
4. Review and guarded market-share calculations.
5. Overview and module screens.
6. End-to-end, PostgreSQL, build, and documentation verification.

## Acceptance

The normal UI workflow must work without manual database edits. Every configured SKU must show supported values or explicit unknown states. Every lagging result must have an inspectable gap or a reason it is not actionable. Reprocessing must be idempotent. Live claims require a real source-backed run.
