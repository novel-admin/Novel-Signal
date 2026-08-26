# Novel Signal

Evidence-first competitive intelligence for Novel across Amazon, Google, and Meta.

Week 1 source boundaries include Amazon SP-API, Amazon Ads API, permitted Brand Analytics reports, Google Search Console, Meta Marketing API, supported Meta Ad Library access, and approved public Amazon.in competitor collection. The scaffold reports whether credentials are configured; live synchronization clients are the next implementation layer.

## Stack

- Next.js and TypeScript web application
- FastAPI and SQLAlchemy backend
- Supabase PostgreSQL and private Supabase Storage
- Render API and database-backed Render Cron collection process
- Vercel Next.js dashboard
- Playwright-ready approved public collection process

## Production deployment

The MVP deploys with three managed platforms only:

1. Deploy `apps/web` to Vercel and set `NEXT_PUBLIC_API_URL` to the Render API.
2. Deploy the FastAPI Docker service from `render.yaml` to Render.
3. Configure Supabase PostgreSQL and a private `novel-signal-raw` Storage bucket.
4. Add source credentials only in Render environment settings.
5. Run `alembic -c apps/backend/alembic.ini upgrade head` against Supabase.
6. Enable the hourly Render cron command after source readiness is verified.

Render Cron runs `python -m novel_signal.cli collect-due`. It plans, claims, and
processes a bounded batch directly from PostgreSQL; Redis and Celery are not
required in production.

## Start locally

1. Copy `.env.example` to `.env`.
2. Enable pnpm: `corepack enable`.
3. Install web dependencies: `pnpm install`.
4. Create a Python 3.13 virtual environment and install the backend: `pip install -e ".[dev]"`.
5. Start optional local dependencies: `docker compose -f infra/compose.yaml up -d postgres minio`.
6. Run migrations: `alembic -c apps/backend/alembic.ini upgrade head`.
7. Start the API: `uvicorn novel_signal.main:app --app-dir apps/backend/src --reload`.
8. Start the web app: `pnpm dev:web`.

See [PRD.md](./PRD.md), [SPEC.md](./SPEC.md), and [IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md).
