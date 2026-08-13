# Local setup

1. Install Node 22, enable Corepack, and use Python 3.13.
2. Copy `.env.example` to `.env`.
3. Run `pnpm install` and `pip install -e ".[dev]"`.
4. Start PostgreSQL, Redis, and MinIO with Docker Compose.
5. Run Alembic migrations.
6. Start FastAPI and Next.js using the commands in the root README.

Local collection is not enabled by this scaffold.
