# Novel Signal

Week 1 foundation for the Amazon.in competitive watchtower.

Week 1 source boundaries include Amazon SP-API, Amazon Ads API, permitted Brand Analytics reports, Google Search Console, Meta Marketing API, supported Meta Ad Library access, and approved public Amazon.in competitor collection. The scaffold reports whether credentials are configured; live synchronization clients are the next implementation layer.

## Stack

- Next.js and TypeScript web application
- FastAPI and SQLAlchemy backend
- PostgreSQL, Redis, Celery, and MinIO
- Playwright-ready collection process

## Start locally

1. Copy `.env.example` to `.env`.
2. Enable pnpm: `corepack enable`.
3. Install web dependencies: `pnpm install`.
4. Create a Python 3.13 virtual environment and install the backend: `pip install -e ".[dev]"`.
5. Start dependencies: `docker compose -f infra/compose.yaml up -d postgres redis minio`.
6. Run migrations: `alembic -c apps/backend/alembic.ini upgrade head`.
7. Start the API: `uvicorn novel_signal.main:app --app-dir apps/backend/src --reload`.
8. Start the web app: `pnpm dev:web`.

See [PRD.md](./PRD.md), [SPEC.md](./SPEC.md), and [IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md).
