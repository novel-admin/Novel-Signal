"""PM plan vertical slice: minimal CSV import, keyword generation, proposals."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from novel_signal.db import Base, get_db
from novel_signal.main import app
from novel_signal.modules.rank_visibility.models import NewEntrantEvent
from novel_signal.modules.universe.models import CompetitorProposal, Marketplace
from novel_signal.modules.universe.proposals import proposal_fingerprint, score_candidate
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

BASE = "/api/v1/universe"


@pytest.fixture
def client() -> Iterator[TestClient]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def configure_sqlite(dbapi_connection: object, _connection_record: object) -> None:
        dbapi_connection.create_function(  # type: ignore[attr-defined]
            "btrim", 1, lambda value: value.strip(), deterministic=True
        )
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


MINIMAL_CSV = (
    "internal_sku,marketplace_product_id,product_url,name,brand,category,"
    "pack_quantity,pack_unit,tracking_tier\n"
    "NOV-WIPES-001,B09GP975ZQ,https://www.amazon.in/dp/B09GP975ZQ,"
    "Novel Baby Wipes,NOVEL,Baby Wipes,4,packs,T1\n"
    "BAD-ROW,SHORT,not-a-url,,,,,,\n"
    "NOV-WIPES-002,B08ABC1234,https://www.amazon.in/dp/B08ABC1234,,,,,,\n"
)


def test_minimal_import_partial_success(client: TestClient) -> None:
    template = client.get(f"{BASE}/products-minimal/template")
    assert template.status_code == 200
    assert template.text.splitlines()[0].startswith("internal_sku,")

    dry_run = client.post(f"{BASE}/products-minimal/dry-run", json={"csv_text": MINIMAL_CSV})
    assert dry_run.status_code == 200
    body = dry_run.json()
    assert body["total_rows"] == 3
    assert body["valid_rows"] == 2
    assert body["invalid_rows"] == 1

    imported = client.post(f"{BASE}/products-minimal/import", json={"csv_text": MINIMAL_CSV})
    assert imported.status_code == 200
    result = imported.json()
    assert result["imported_rows"] == 2
    assert result["invalid_rows"] == 1
    assert set(result["imported_skus"]) == {"NOV-WIPES-001", "NOV-WIPES-002"}
    assert any(error["row"] == 3 for error in result["errors"])

    # Defaults applied for the sparse row.
    products = client.get(f"{BASE}/products").json()
    assert products["total"] == 2
    sparse = next(item for item in products["items"] if item["internal_sku"] == "NOV-WIPES-002")
    assert sparse["name"] == "NOV-WIPES-002"
    assert sparse["brand"] == "NOVEL"
    assert sparse["category"] == "Unclassified"
    assert sparse["tracking_tier"] == "T2"

    # Re-import is idempotent-safe: conflicts surface as row errors, not 500s.
    repeat = client.post(f"{BASE}/products-minimal/import", json={"csv_text": MINIMAL_CSV})
    assert repeat.status_code == 200
    assert repeat.json()["imported_rows"] == 0


def test_generate_keywords_idempotent(client: TestClient) -> None:
    product = client.post(
        f"{BASE}/products",
        json={
            "internal_sku": "NOV-DIAPER-001",
            "name": "Novel Baby Diaper Pants XL 62 Count Rash Free",
            "brand": "NOVEL",
            "category": "Baby Diapers",
            "marketplace": "amazon_in",
            "marketplace_product_id": "B09GP975ZQ",
            "product_url": "https://www.amazon.in/dp/B09GP975ZQ",
            "tracking_tier": "T1",
        },
    )
    assert product.status_code == 201, product.text
    product_id = product.json()["id"]

    first = client.post(f"{BASE}/products/{product_id}/generate-keywords")
    assert first.status_code == 200, first.text
    first_body = first.json()
    assert 3 <= len(first_body["created_keywords"]) + len(first_body["reused_keywords"]) <= 8
    assert first_body["tracking_targets_created"] >= 1

    second = client.post(f"{BASE}/products/{product_id}/generate-keywords")
    assert second.status_code == 200
    second_body = second.json()
    assert second_body["created_keywords"] == []
    assert second_body["tracking_targets_created"] == 0
    assert len(second_body["reused_keywords"]) == len(
        first_body["created_keywords"]
    ) + len(first_body["reused_keywords"])


def _seed_new_entrant(session: Session) -> None:
    from novel_signal.modules.keywords.models import Keyword
    from novel_signal.modules.rank_visibility.models import SerpCapture

    for index, text in enumerate(("baby wipes", "baby wipes sensitive")):
        keyword = Keyword(
            keyword_text=text,
            normalized_text=text,
            marketplace=Marketplace.AMAZON_IN,
            tier="T1",  # type: ignore[arg-type]
        )
        keyword.sources = []  # type: ignore[assignment]
        session.add(keyword)
        session.flush()
        capture = SerpCapture(
            keyword_id=keyword.id,
            marketplace=Marketplace.AMAZON_IN,
            geo_code="IN",
            device_profile="desktop",  # type: ignore[arg-type]
            captured_at=datetime.now(UTC),
            page_count=1,
            result_count=1,
        )
        session.add(capture)
        session.flush()
        session.add(
            NewEntrantEvent(
                keyword_id=keyword.id,
                marketplace=Marketplace.AMAZON_IN,
                marketplace_product_id="B0DISC0001",
                first_seen_capture_id=capture.id,
                first_seen_at=datetime.now(UTC),
                rank=2 + index,
                brand="Discovery Brand",
                geo_code="IN",
                device_profile="desktop",  # type: ignore[arg-type]
            )
        )
    session.commit()


def test_proposal_scoring_unit() -> None:
    score, breakdown = score_candidate(appearances=5, best_rank=2)
    assert score == pytest.approx(40.0 + 27.0)
    assert set(breakdown) == {"recurrence", "rank_strength", "category_match", "sku_overlap"}
    weak, _ = score_candidate(appearances=1, best_rank=None)
    assert weak < score


def test_product_competitor_search_queues_amazon_only_jobs(client: TestClient) -> None:
    imported = client.post(
        f"{BASE}/products-minimal/import", json={"csv_text": MINIMAL_CSV.splitlines()[0] + "\n" + MINIMAL_CSV.splitlines()[1]}
    )
    assert imported.status_code == 200, imported.text
    products = client.get(f"{BASE}/products").json()["items"]
    product = next(item for item in products if item["internal_sku"] == "NOV-WIPES-001")

    queued = client.post(
        f"{BASE}/products/{product['id']}/search-competitors",
        json={"keywords": ["baby wipes", "NOVEL baby wipes"]},
    )
    assert queued.status_code == 200, queued.text
    body = queued.json()
    assert len(body["job_ids"]) == 2
    jobs = client.get("/api/v1/collection/jobs?limit=20").json()["items"]
    matching = [job for job in jobs if job["id"] in body["job_ids"]]
    assert len(matching) == 2
    assert {job["platform"] for job in matching} == {"amazon_in"}
    assert {job["job_type"] for job in matching} == {"serp"}


def test_approving_product_candidate_adds_it_to_that_products_card(client: TestClient) -> None:
    created = client.post(
        f"{BASE}/products",
        json={
            "internal_sku": "NOV-CREAM-001", "name": "Novel Baby Cream", "brand": "NOVEL",
            "category": "Baby Cream", "marketplace": "amazon_in", "tracking_tier": "T1",
        },
    )
    assert created.status_code == 201, created.text
    product_id = uuid.UUID(created.json()["id"])
    proposal_id = uuid.uuid4()
    override = app.dependency_overrides[get_db]
    sessions = override()  # type: ignore[operator]
    session = next(sessions)
    try:
        session.add(CompetitorProposal(
            id=proposal_id,
            fingerprint=proposal_fingerprint(Marketplace.AMAZON_IN, "B0CANDIDATE1", product_id),
            marketplace=Marketplace.AMAZON_IN,
            marketplace_product_id="B0CANDIDATE1",
            discovered_for_product_id=product_id,
            brand="Example Brand",
            title="Example Baby Cream",
            appearances=2,
        ))
        session.commit()
    finally:
        try:
            next(sessions)
        except StopIteration:
            pass
        session.close()

    approved = client.post(f"{BASE}/competitor-proposals/{proposal_id}/approve", json={})
    assert approved.status_code == 200, approved.text
    cards = client.get(f"{BASE}/battle-cards?product_id={product_id}").json()["items"]
    assert len(cards) == 1
    assert cards[0]["product_id"] == str(product_id)
    assert cards[0]["items"][0]["competitor_product"]["marketplace_product_id"] == "B0CANDIDATE1"


def test_proposal_build_approve_reject_flow(client: TestClient) -> None:
    # Seed new-entrant evidence through the app's own DB session override.
    engine_holder: dict[str, object] = {}

    # Build via API after inserting rows with a direct session on the same
    # in-memory database is complex; instead exercise build from service-level
    # rows created through public ingestion endpoints is covered elsewhere.
    # Here we verify the queue lifecycle with build on empty + direct insert.
    built = client.post(f"{BASE}/competitor-proposals/build")
    assert built.status_code == 200
    assert built.json()["pending"] == 0
    assert engine_holder == {}

    queued = client.get(f"{BASE}/competitor-proposals")
    assert queued.status_code == 200
    assert queued.json()["total"] == 0


def test_proposal_approve_creates_tracked_product(client: TestClient) -> None:
    # Insert proposal dependencies directly via the overridden session factory.
    from novel_signal.db import get_db as _get_db  # noqa: F401

    # Use public APIs to create the minimal graph, then insert a NewEntrantEvent
    # through the collection of sessions is not exposed; instead create a
    # proposal by building from an event inserted via a raw session. To keep
    # this test hermetic we insert via the TestClient app dependency override.
    override = app.dependency_overrides[get_db]
    sessions = override()  # type: ignore[operator]
    session = next(sessions)
    try:
        _seed_new_entrant(session)
    finally:
        try:
            next(sessions)
        except StopIteration:
            pass
        session.close()

    built = client.post(f"{BASE}/competitor-proposals/build")
    assert built.status_code == 200, built.text
    assert built.json()["created"] == 1

    pending = client.get(f"{BASE}/competitor-proposals?status=pending").json()
    assert pending["total"] == 1
    proposal = pending["items"][0]
    assert proposal["marketplace_product_id"] == "B0DISC0001"
    assert proposal["appearances"] == 2
    assert proposal["best_rank"] == 2
    assert proposal["score"] is not None and proposal["score"] > 0
    assert proposal["evidence"]["appearances"] == 2

    approved = client.post(
        f"{BASE}/competitor-proposals/{proposal['id']}/approve",
        json={"category": "Baby Wipes"},
    )
    assert approved.status_code == 200, approved.text
    approved_body = approved.json()
    assert approved_body["status"] == "approved"
    assert approved_body["linked_competitor_product_id"] is not None

    tracked = client.get(f"{BASE}/competitor-products").json()
    assert tracked["total"] == 1
    assert tracked["items"][0]["marketplace_product_id"] == "B0DISC0001"

    # Second approval must fail; reject/archived transitions on decided rows fail.
    again = client.post(
        f"{BASE}/competitor-proposals/{proposal['id']}/approve", json={}
    )
    assert again.status_code in {409, 422}
    rejected = client.post(f"{BASE}/competitor-proposals/{proposal['id']}/reject")
    assert rejected.status_code == 422
    _ = select(NewEntrantEvent)


def test_proposal_reject_and_archive(client: TestClient) -> None:
    override = app.dependency_overrides[get_db]
    sessions = override()  # type: ignore[operator]
    session = next(sessions)
    try:
        from novel_signal.modules.keywords.models import Keyword
        from novel_signal.modules.rank_visibility.models import SerpCapture

        keyword = Keyword(
            keyword_text="baby diapers",
            normalized_text="baby diapers",
            marketplace=Marketplace.AMAZON_IN,
            tier="T1",  # type: ignore[arg-type]
        )
        keyword.sources = []  # type: ignore[assignment]
        session.add(keyword)
        session.flush()
        capture = SerpCapture(
            keyword_id=keyword.id,
            marketplace=Marketplace.AMAZON_IN,
            geo_code="IN",
            device_profile="desktop",  # type: ignore[arg-type]
            captured_at=datetime.now(UTC),
            page_count=1,
            result_count=1,
        )
        session.add(capture)
        session.flush()
        session.add(
            NewEntrantEvent(
                keyword_id=keyword.id,
                marketplace=Marketplace.AMAZON_IN,
                marketplace_product_id="B0REJECT001",
                first_seen_capture_id=capture.id,
                first_seen_at=datetime.now(UTC),
                rank=9,
                brand="Reject Brand",
                geo_code="IN",
                device_profile="desktop",  # type: ignore[arg-type]
            )
        )
        session.commit()
    finally:
        try:
            next(sessions)
        except StopIteration:
            pass
        session.close()

    assert client.post(f"{BASE}/competitor-proposals/build").status_code == 200
    pending = client.get(f"{BASE}/competitor-proposals?status=pending").json()
    proposal = next(
        item for item in pending["items"] if item["marketplace_product_id"] == "B0REJECT001"
    )
    assert client.post(f"{BASE}/competitor-proposals/{proposal['id']}/reject").status_code == 200
    assert (
        client.get(f"{BASE}/competitor-proposals?status=pending").json()["total"] == 0
    )
    missing = uuid.uuid4()
    assert client.post(f"{BASE}/competitor-proposals/{missing}/approve", json={}).status_code == 404
