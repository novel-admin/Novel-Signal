from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from novel_signal.db import Base, get_db
from novel_signal.main import app
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

BASE = "/api/v1/collection"


@pytest.fixture
def client() -> Iterator[TestClient]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def configure_sqlite(dbapi_connection: object, _connection_record: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)

    def override_db() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_collection_meta_and_empty_jobs(client: TestClient) -> None:
    meta = client.get(f"{BASE}/meta")
    assert meta.status_code == 200
    assert meta.json() == {"module": "S12 Collection", "status": "phase-4"}

    jobs = client.get(f"{BASE}/jobs")
    assert jobs.status_code == 200
    assert jobs.json() == {"items": [], "total": 0, "limit": 50, "offset": 0}


def test_missing_job_returns_structured_404(client: TestClient) -> None:
    response = client.get(f"{BASE}/jobs/00000000-0000-4000-8000-000000000000")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "collection_job_not_found"
