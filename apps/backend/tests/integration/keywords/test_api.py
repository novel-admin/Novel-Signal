from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from novel_signal.db import Base, get_db
from novel_signal.main import app
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

BASE = "/api/v1/keywords"


@pytest.fixture
def client() -> Iterator[TestClient]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def sqlite_config(connection: object, _: object) -> None:
        connection.create_function("btrim", 1, lambda value: value.strip(), deterministic=True)  # type: ignore[attr-defined]
        cursor = connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)

    def override() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = override
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()


def keyword_payload(text: str = "baby diapers", **extra: Any) -> dict[str, Any]:
    return {
        "keyword_text": text,
        "marketplace": "amazon_in",
        "category": "Baby Care",
        "tier": "T1",
        "tracking_status": "active",
        "intent_cluster": "generic_category",
        "sources": [{"source_type": "manual"}],
        **extra,
    }


def create_keyword(client: TestClient, text: str = "baby diapers", **extra: Any) -> dict[str, Any]:
    response = client.post(BASE, json=keyword_payload(text, **extra))
    assert response.status_code == 201, response.text
    return response.json()


def create_s1_targets(client: TestClient) -> tuple[dict[str, Any], dict[str, Any]]:
    product = client.post(
        "/api/v1/universe/products",
        json={
            "internal_sku": "KW-OWN-1",
            "name": "Owned",
            "brand": "Owned",
            "category": "Baby Care",
            "marketplace": "amazon_in",
            "marketplace_product_id": "B000009991",
            "tracking_tier": "T1",
        },
    ).json()
    competitor = client.post(
        "/api/v1/universe/competitors", json={"name": "Keyword Target Competitor"}
    ).json()
    competitor_product = client.post(
        "/api/v1/universe/competitor-products",
        json={
            "competitor_id": competitor["id"],
            "name": "External",
            "brand": "External",
            "category": "Baby Care",
            "marketplace": "amazon_in",
            "marketplace_product_id": "B000009992",
            "tracking_tier": "T1",
        },
    ).json()
    return product, competitor_product


def test_keyword_normalization_provenance_filters_pagination_and_bulk(client: TestClient) -> None:
    keyword = create_keyword(
        client,
        "  Baby   Diapers  ",
        sources=[
            {"source_type": "manual"},
            {"source_type": "amazon_ads", "source_reference": "report-1"},
        ],
        volume_estimate=100,
    )
    assert (
        keyword["keyword_text"] == "Baby Diapers" and keyword["normalized_text"] == "baby diapers"
    )
    assert len(keyword["sources"]) == 2
    duplicate = client.post(BASE, json=keyword_payload("baby diapers"))
    assert duplicate.status_code == 409
    second = create_keyword(
        client,
        "rash free diaper",
        tier="T2",
        tracking_status="paused",
        intent_cluster="problem_benefit",
    )
    assert (
        client.get(
            BASE,
            params={
                "search": "RASH",
                "tier": "T2",
                "tracking_status": "paused",
                "intent_cluster": "problem_benefit",
                "source": "manual",
                "marketplace": "amazon_in",
                "category": "baby",
            },
        ).json()["total"]
        == 1
    )
    page = client.get(BASE, params={"limit": 1, "offset": 1}).json()
    assert (page["total"], len(page["items"])) == (2, 1)
    assert client.get(BASE, params={"priority_only": True}).json()["total"] == 1
    updated = client.patch(
        f"{BASE}/{second['id']}",
        json={
            "tier": "T1",
            "tracking_status": "active",
            "sources": [{"source_type": "review_mining"}],
        },
    )
    assert {item["source_type"] for item in updated.json()["sources"]} == {
        "manual",
        "review_mining",
    }
    bulk = client.post(
        f"{BASE}/bulk/update",
        json={
            "keyword_ids": [keyword["id"], second["id"]],
            "tier": "T3",
            "tracking_status": "paused",
        },
    )
    assert bulk.json()["updated"] == 2
    assert client.get(BASE, params={"priority_only": True}).json()["total"] == 0


def test_duplicate_source_in_one_payload_is_rejected(client: TestClient) -> None:
    response = client.post(
        BASE,
        json=keyword_payload(
            sources=[
                {"source_type": "manual", "source_reference": "same"},
                {"source_type": "manual", "source_reference": "same"},
            ]
        ),
    )
    assert response.status_code == 422


def test_keyword_archive_restore_and_conflict(client: TestClient) -> None:
    first = create_keyword(client, "baby wipes")
    assert client.post(f"{BASE}/{first['id']}/archive").status_code == 200
    assert client.get(BASE).json()["total"] == 0
    replacement = create_keyword(client, " Baby   Wipes ")
    restore = client.post(f"{BASE}/{first['id']}/restore")
    assert restore.status_code == 409
    client.post(f"{BASE}/{replacement['id']}/archive")
    assert client.post(f"{BASE}/{first['id']}/restore").status_code == 200
    assert client.get(f"{BASE}/00000000-0000-4000-8000-000000000000").status_code == 404


def test_tracking_targets_complete_rules_lifecycle_and_filters(client: TestClient) -> None:
    keyword = create_keyword(client)
    product, competitor_product = create_s1_targets(client)
    neither = client.post(
        f"{BASE}/tracking-targets", json={"keyword_id": keyword["id"], "cadence_minutes": 240}
    )
    assert neither.status_code == 422
    both = client.post(
        f"{BASE}/tracking-targets",
        json={
            "keyword_id": keyword["id"],
            "product_id": product["id"],
            "competitor_product_id": competitor_product["id"],
        },
    )
    assert both.status_code == 422
    own = client.post(
        f"{BASE}/tracking-targets",
        json={"keyword_id": keyword["id"], "product_id": product["id"], "cadence_minutes": 240},
    )
    assert own.status_code == 201 and own.json()["cadence_minutes"] == 240
    external = client.post(
        f"{BASE}/tracking-targets",
        json={
            "keyword_id": keyword["id"],
            "competitor_product_id": competitor_product["id"],
        },
    )
    assert external.status_code == 201 and external.json()["cadence_minutes"] == 240
    assert (
        client.post(
            f"{BASE}/tracking-targets",
            json={"keyword_id": keyword["id"], "product_id": product["id"]},
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"{BASE}/tracking-targets",
            json={"keyword_id": keyword["id"], "product_id": product["id"], "cadence_minutes": 0},
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"{BASE}/tracking-targets",
            json={
                "keyword_id": keyword["id"],
                "competitor_product_id": competitor_product["id"],
                "cadence_minutes": -1,
            },
        ).status_code
        == 422
    )
    assert (
        client.get(
            f"{BASE}/tracking-targets",
            params={"keyword_id": keyword["id"], "enabled": True, "cadence_minutes": 240},
        ).json()["total"]
        == 2
    )
    changed = client.patch(
        f"{BASE}/tracking-targets/{own.json()['id']}",
        json={"enabled": False, "cadence_minutes": 480},
    )
    assert changed.json()["cadence_minutes"] == 480
    client.post(f"{BASE}/tracking-targets/{own.json()['id']}/archive")
    replacement = client.post(
        f"{BASE}/tracking-targets", json={"keyword_id": keyword["id"], "product_id": product["id"]}
    ).json()
    assert client.post(f"{BASE}/tracking-targets/{own.json()['id']}/restore").status_code == 409
    client.post(f"{BASE}/tracking-targets/{replacement['id']}/archive")
    assert client.post(f"{BASE}/tracking-targets/{own.json()['id']}/restore").status_code == 200


def test_archived_dependencies_and_missing_references_are_rejected(client: TestClient) -> None:
    keyword = create_keyword(client)
    product, _ = create_s1_targets(client)
    client.post(f"{BASE}/{keyword['id']}/archive")
    assert (
        client.post(
            f"{BASE}/tracking-targets",
            json={"keyword_id": keyword["id"], "product_id": product["id"]},
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"{BASE}/tracking-targets",
            json={
                "keyword_id": "00000000-0000-4000-8000-000000000000",
                "product_id": product["id"],
            },
        ).status_code
        == 404
    )
    client.post(f"{BASE}/{keyword['id']}/restore")
    client.post(f"/api/v1/universe/products/{product['id']}/archive")
    assert (
        client.post(
            f"{BASE}/tracking-targets",
            json={"keyword_id": keyword["id"], "product_id": product["id"]},
        ).status_code
        == 422
    )
