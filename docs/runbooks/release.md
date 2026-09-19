# Release scaffold

Before release:

- Run backend lint, type checks, and tests.
- Run frontend lint, type checks, tests, and production build.
- Apply migrations in the target environment.
- Confirm readiness endpoints.
- Confirm production collection remains disabled until its legal and location inputs are approved.

## Render deployment (PM §3: one web service + PostgreSQL + object store)

- `render.yaml` provisions `novel-signal-api` (Docker web) and `novel-signal-db`
  (PostgreSQL). No Cron service, Redis, Celery, or background worker is required:
  the web service runs the internal PostgreSQL-backed scheduler on FastAPI
  lifespan and processes collection in bounded batches.
- `preDeployCommand` runs `alembic -c apps/backend/alembic.ini upgrade head` as
  the release migration step before every deploy.
- Required service env vars: `DATABASE_URL` (from database), `INTERNAL_AUTH_SECRET`
  (generated), `ALLOWED_ORIGINS`, `OBJECT_STORE_ENDPOINT/BUCKET/ACCESS_KEY/SECRET_KEY/REGION`,
  `COLLECTION_BATCH_SIZE`, `INTERNAL_SCHEDULER_ENABLED`,
  `INTERNAL_SCHEDULER_INTERVAL_SECONDS`, plus optional provider credentials
  (`AMAZON_*`, `GOOGLE_*`, `META_*`). Missing API credentials leave dependent
  values labelled `not connected` / `unknown`, never zero.
- Local/emergency runs: `python -m novel_signal.cli collect-due` remains available
  for bounded manual collection outside the scheduler.
- Verify after deploy: `GET /api/v1/health/live`, `GET /api/v1/collection/readiness`,
  and one Alembic head (`alembic heads` shows a single head).
