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


def test_resync_accepts_bounded_filters(client: TestClient) -> None:
    response = client.post(
        f"{BASE}/resync",
        json={
            "sources": ["amazon_public_pages"],
            "window_start": "2026-08-26T00:00:00Z",
            "window_end": "2026-08-27T00:00:00Z",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"created": 0, "existing": 0, "job_ids": []}


def test_resync_rejects_unknown_source_and_large_window(client: TestClient) -> None:
    unknown = client.post(f"{BASE}/resync", json={"sources": ["flipkart"]})
    assert unknown.status_code == 422
    assert unknown.json()["detail"]["code"] == "unsupported_resync_source"

    large = client.post(
        f"{BASE}/resync",
        json={
            "window_start": "2026-01-01T00:00:00Z",
            "window_end": "2026-02-02T00:00:00Z",
        },
    )
    assert large.status_code == 422
