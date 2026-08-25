# Palguna Intelligence Release Status

Date: 25 August 2026
Branch: `feat/palguna-intelligence-delivery`

## Locally verified capability

- Published observations require raw evidence and parser lineage.
- Quarantined and unpublished reviews do not reach topic or trend metrics.
- Scorecards support scored, stale, and explicit unknown states.
- Critical scorecards idempotently create a gap, recommended action, and linked alert.
- Actions can originate from gaps or changes and require owner plus due date before activation.
- Alerts persist, deduplicate, acknowledge, and resolve.
- Amazon Ads requests use profile scope headers and bounded asynchronous report polling.
- Amazon Ads report bodies are stored as S12 raw evidence before versioned parsing.
- Search-term contributions retain measured metrics, report identity, raw evidence, and parser lineage.
- Competitor sponsored presence uses successful captures as its denominator.
- Ad summaries expose continuous days, total days, keyword breadth, slot share, position, and daypart profiles.
- Review metrics expose count, average rating, velocity, trajectory, sample size, and confidence.
- Market-share models refuse small, low-coverage, or lineage-free inputs.
- Overview, ads, reviews, market-share, scorecard, and alert routes are API-backed.

## Verification completed

- Ruff passed.
- Strict mypy passed across 124 backend source files.
- Local backend suite: 152 passed and 6 PostgreSQL tests skipped.
- Frontend: 14 tests passed.
- Frontend typecheck passed.
- Frontend production build passed.
- Alembic reports one head: `20260825_03`.
- PostgreSQL offline migration SQL generation passed.

## Not live verified

- Amazon Ads credentials, profile permissions, report types, and real report download.
- PostgreSQL upgrade and downgrade against a running server because Docker Desktop was unavailable.
- MinIO object storage against a running service.
- Scheduled Celery execution against Redis.
- A real Akanksh-published dataset through every intelligence screen.

These items must not be described as live until their real source-backed checks pass.
