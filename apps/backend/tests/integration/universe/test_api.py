from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from novel_signal.db import Base, get_db
from novel_signal.main import app
from sqlalchemy import create_engine, event
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


def create_competitor(client: TestClient, name: str = "Acme", **extra: Any) -> dict[str, Any]:
    response = client.post(f"{BASE}/competitors", json={"name": name, **extra})
    assert response.status_code == 201, response.text
    return response.json()


def product_payload(sku: str = "OWN-001", asin: str = "b000000001") -> dict[str, Any]:
    return {
        "internal_sku": sku,
        "name": f"Owned {sku}",
        "brand": "Owned Brand",
        "category": "Baby Care",
        "marketplace": "amazon_in",
        "marketplace_product_id": asin,
        "pack_quantity": 10,
        "pack_unit": "pieces",
        "tracking_tier": "T1",
    }


def create_product(client: TestClient, **overrides: Any) -> dict[str, Any]:
    payload = {**product_payload(), **overrides}
    response = client.post(f"{BASE}/products", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def create_competitor_product(
    client: TestClient, competitor_id: str, asin: str = "b000000002", **overrides: Any
) -> dict[str, Any]:
    payload = {
        "competitor_id": competitor_id,
        "name": "Acme Product",
        "brand": "Acme",
        "category": "Baby Care",
        "marketplace": "amazon_in",
        "marketplace_product_id": asin,
        "pack_quantity": 12,
        "pack_unit": "pieces",
        "tracking_tier": "T1",
        **overrides,
    }
    response = client.post(f"{BASE}/competitor-products", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def create_battle_card(client: TestClient, product_id: str, **overrides: Any) -> dict[str, Any]:
    response = client.post(
        f"{BASE}/battle-cards",
        json={"product_id": product_id, "name": "Primary comparison", **overrides},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_competitor_full_lifecycle_filters_pagination_and_restore_conflict(
    client: TestClient,
) -> None:
    acme = create_competitor(
        client,
        positioning_tier="mid",
        category_presence="Baby Care, Wipes",
        threat_rating=4,
    )
    create_competitor(client, "Beta", positioning_tier="premium")
    assert client.get(f"{BASE}/competitors/{acme['id']}").status_code == 200
    assert client.get(f"{BASE}/competitors/00000000-0000-4000-8000-000000000000").status_code == 404
    updated = client.patch(
        f"{BASE}/competitors/{acme['id']}", json={"analyst_owner": "Analyst One"}
    )
    assert updated.json()["analyst_owner"] == "Analyst One"
    assert client.get(f"{BASE}/competitors", params={"search": "acm"}).json()["total"] == 1
    assert (
        client.get(f"{BASE}/competitors", params={"category_presence": "wipes"}).json()["total"]
        == 1
    )
    page = client.get(f"{BASE}/competitors", params={"limit": 1, "offset": 1}).json()
    assert (page["total"], len(page["items"]), page["limit"], page["offset"]) == (2, 1, 1, 1)

    assert client.post(f"{BASE}/competitors/{acme['id']}/archive").status_code == 200
    assert client.get(f"{BASE}/competitors/{acme['id']}").status_code == 200
    assert client.get(f"{BASE}/competitors").json()["total"] == 1
    assert client.get(f"{BASE}/competitors", params={"include_archived": True}).json()["total"] == 2
    create_competitor(client, " acme ")
    restore = client.post(f"{BASE}/competitors/{acme['id']}/restore")
    assert restore.status_code == 409
    assert restore.json()["detail"]["code"] == "competitor_conflict"
    assert client.post(f"{BASE}/competitors", json={"name": "ACME"}).status_code == 409


def test_product_validation_filters_archive_and_restore_conflicts(client: TestClient) -> None:
    product = create_product(client)
    assert product["marketplace_product_id"] == "B000000001"
    assert client.get(f"{BASE}/products/{product['id']}").status_code == 200
    assert (
        client.patch(f"{BASE}/products/{product['id']}", json={"brand": "New Brand"}).json()[
            "brand"
        ]
        == "New Brand"
    )
    assert client.get(f"{BASE}/products", params={"internal_sku": "OWN"}).json()["total"] == 1
    assert client.get(f"{BASE}/products", params={"brand": "new"}).json()["total"] == 1
    assert client.get(f"{BASE}/products", params={"category": "baby"}).json()["total"] == 1
    assert client.get(f"{BASE}/products", params={"marketplace": "amazon_in"}).json()["total"] == 1
    assert client.get(f"{BASE}/products", params={"tracking_tier": "T1"}).json()["total"] == 1
    assert (
        client.post(f"{BASE}/products", json=product_payload("OWN-002", "bad")).status_code == 422
    )
    assert (
        client.post(f"{BASE}/products", json=product_payload("OWN-001", "B000000003")).status_code
        == 409
    )
    assert (
        client.post(f"{BASE}/products", json=product_payload("OWN-003", "B000000001")).status_code
        == 409
    )

    client.post(f"{BASE}/products/{product['id']}/archive")
    replacement = create_product(
        client, internal_sku="OWN-001", marketplace_product_id="B000000001"
    )
    assert replacement["id"] != product["id"]
    restore = client.post(f"{BASE}/products/{product['id']}/restore")
    assert restore.status_code == 409
    assert restore.json()["detail"]["code"] in {"product_sku_conflict", "product_identity_conflict"}


def test_competitor_product_rules_update_and_filters(client: TestClient) -> None:
    competitor = create_competitor(client)
    other_competitor = create_competitor(client, "Other competitor")
    item = create_competitor_product(client, competitor["id"])
    assert item["marketplace_product_id"] == "B000000002"
    assert client.get(f"{BASE}/competitor-products/{item['id']}").status_code == 200
    assert (
        client.patch(
            f"{BASE}/competitor-products/{item['id']}", json={"brand": "Acme Plus"}
        ).json()["brand"]
        == "Acme Plus"
    )
    assert (
        client.get(
            f"{BASE}/competitor-products", params={"competitor_id": competitor["id"]}
        ).json()["total"]
        == 1
    )
    assert client.get(f"{BASE}/competitor-products", params={"brand": "plus"}).json()["total"] == 1
    assert (
        client.get(f"{BASE}/competitor-products", params={"category": "baby"}).json()["total"] == 1
    )
    assert (
        client.get(f"{BASE}/competitor-products", params={"marketplace": "amazon_in"}).json()[
            "total"
        ]
        == 1
    )
    assert (
        client.get(f"{BASE}/competitor-products", params={"tracking_tier": "T1"}).json()["total"]
        == 1
    )
    duplicate = client.post(
        f"{BASE}/competitor-products",
        json={
            "competitor_id": competitor["id"],
            "name": "Duplicate",
            "brand": "Acme",
            "category": "Baby Care",
            "marketplace_product_id": "B000000002",
            "tracking_tier": "T1",
        },
    )
    assert duplicate.status_code == 409
    cross_competitor_duplicate = client.post(
        f"{BASE}/competitor-products",
        json={
            "competitor_id": other_competitor["id"],
            "name": "Cross competitor duplicate",
            "brand": "Other",
            "category": "Baby Care",
            "marketplace_product_id": "B000000002",
            "tracking_tier": "T1",
        },
    )
    assert cross_competitor_duplicate.status_code == 409
    assert cross_competitor_duplicate.json()["detail"]["code"] == "competitor_product_conflict"

    assert client.post(f"{BASE}/competitor-products/{item['id']}/archive").status_code == 200
    replacement = create_competitor_product(
        client,
        other_competitor["id"],
        asin="B000000002",
        name="Replacement listing owner",
    )
    assert replacement["id"] != item["id"]
    restore = client.post(f"{BASE}/competitor-products/{item['id']}/restore")
    assert restore.status_code == 409
    assert (
        client.post(
            f"{BASE}/competitor-products",
            json={
                "competitor_id": competitor["id"],
                "name": "Invalid",
                "brand": "Acme",
                "category": "Baby Care",
                "marketplace_product_id": "bad",
                "tracking_tier": "T1",
            },
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"{BASE}/competitor-products",
            json={
                "competitor_id": "00000000-0000-4000-8000-000000000000",
                "name": "Missing",
                "brand": "Acme",
                "category": "Baby Care",
                "tracking_tier": "T1",
            },
        ).status_code
        == 404
    )
    client.post(f"{BASE}/competitors/{competitor['id']}/archive")
    assert (
        client.post(
            f"{BASE}/competitor-products",
            json={
                "competitor_id": competitor["id"],
                "name": "Archived",
                "brand": "Acme",
                "category": "Baby Care",
                "tracking_tier": "T1",
            },
        ).status_code
        == 422
    )


def test_battle_card_rules_lifecycle_and_filters(client: TestClient) -> None:
    product = create_product(client)
    card = create_battle_card(client, product["id"], status="draft")
    assert client.get(f"{BASE}/battle-cards/{card['id']}").status_code == 200
    assert (
        client.patch(f"{BASE}/battle-cards/{card['id']}", json={"status": "approved"}).json()[
            "status"
        ]
        == "approved"
    )
    assert (
        client.get(f"{BASE}/battle-cards", params={"product_id": product["id"]}).json()["total"]
        == 1
    )
    assert client.get(f"{BASE}/battle-cards", params={"status": "approved"}).json()["total"] == 1
    assert (
        client.post(
            f"{BASE}/battle-cards",
            json={"product_id": "00000000-0000-4000-8000-000000000000", "name": "Missing"},
        ).status_code
        == 404
    )
    client.post(f"{BASE}/products/{product['id']}/archive")
    assert (
        client.post(
            f"{BASE}/battle-cards", json={"product_id": product["id"], "name": "Archived"}
        ).status_code
        == 422
    )
    assert client.post(f"{BASE}/battle-cards/{card['id']}/archive").status_code == 200
    assert client.get(f"{BASE}/battle-cards").json()["total"] == 0
    assert (
        client.get(f"{BASE}/battle-cards", params={"include_archived": True}).json()["total"] == 1
    )
    assert client.post(f"{BASE}/battle-cards/{card['id']}/restore").status_code == 422


def test_battle_card_item_complete_lifecycle_filters_and_restore_conflict(
    client: TestClient,
) -> None:
    competitor = create_competitor(client)
    product = create_product(client)
    competitor_product = create_competitor_product(client, competitor["id"])
    card = create_battle_card(client, product["id"])
    payload = {
        "battle_card_id": card["id"],
        "competitor_product_id": competitor_product["id"],
        "priority_order": 0,
        "same_category": True,
    }
    created = client.post(f"{BASE}/battle-card-items", json=payload)
    assert created.status_code == 201, created.text
    item = created.json()
    assert client.get(f"{BASE}/battle-card-items/{item['id']}").status_code == 200
    assert (
        client.patch(
            f"{BASE}/battle-card-items/{item['id']}",
            json={"notes": "Reviewed", "priority_order": 2},
        ).json()["notes"]
        == "Reviewed"
    )
    listed = client.get(f"{BASE}/battle-card-items", params={"battle_card_id": card["id"]}).json()
    assert listed["total"] == 1
    assert (
        client.get(
            f"{BASE}/battle-card-items", params={"competitor_product_id": competitor_product["id"]}
        ).json()["total"]
        == 1
    )
    assert client.post(f"{BASE}/battle-card-items", json=payload).status_code == 409
    assert (
        client.post(f"{BASE}/battle-card-items", json={**payload, "priority_order": -1}).status_code
        == 422
    )

    assert client.post(f"{BASE}/battle-card-items/{item['id']}/archive").status_code == 200
    assert client.get(f"{BASE}/battle-card-items").json()["total"] == 0
    assert (
        client.get(f"{BASE}/battle-card-items", params={"include_archived": True}).json()["total"]
        == 1
    )
    replacement = client.post(f"{BASE}/battle-card-items", json=payload)
    assert replacement.status_code == 201, replacement.text
    restore = client.post(f"{BASE}/battle-card-items/{item['id']}/restore")
    assert restore.status_code == 409
    assert restore.json()["detail"]["code"] == "battle_card_item_conflict"


def test_battle_card_item_rejects_archived_references(client: TestClient) -> None:
    competitor = create_competitor(client)
    product = create_product(client)
    competitor_product = create_competitor_product(client, competitor["id"])
    card = create_battle_card(client, product["id"])
    payload = {"battle_card_id": card["id"], "competitor_product_id": competitor_product["id"]}
    client.post(f"{BASE}/battle-cards/{card['id']}/archive")
    assert client.post(f"{BASE}/battle-card-items", json=payload).status_code == 422
    client.post(f"{BASE}/battle-cards/{card['id']}/restore")
    client.post(f"{BASE}/competitor-products/{competitor_product['id']}/archive")
    assert client.post(f"{BASE}/battle-card-items", json=payload).status_code == 422


def test_all_get_by_id_routes_return_structured_404(client: TestClient) -> None:
    missing = "00000000-0000-4000-8000-000000000000"
    for resource in (
        "competitors",
        "products",
        "competitor-products",
        "battle-cards",
        "battle-card-items",
    ):
        response = client.get(f"{BASE}/{resource}/{missing}")
        assert response.status_code == 404
        assert set(response.json()["detail"]) == {"code", "message"}


def test_openapi_contains_examples_and_all_item_routes(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    assert f"{BASE}/battle-card-items" in schema["paths"]
    assert f"{BASE}/battle-card-items/{{entity_id}}" in schema["paths"]
    for model in (
        "CompetitorCreate",
        "ProductCreate",
        "CompetitorProductCreate",
        "BattleCardCreate",
        "BattleCardItemCreate",
    ):
        assert "example" in schema["components"]["schemas"][model]


def test_collection_readiness_reports_ready_owned_product(client: TestClient) -> None:
    create_product(client, product_url="https://www.amazon.in/dp/B000000001")

    response = client.get(f"{BASE}/readiness")

    assert response.status_code == 200, response.text
    assert response.json() == {
        "ready": True,
        "counts": {
            "products_checked": 1,
            "competitor_products_checked": 0,
            "battle_cards_checked": 0,
            "battle_card_mappings_checked": 0,
        },
        "issue_count": 0,
        "issues": [],
    }


def test_collection_readiness_reports_owned_product_missing_identity(client: TestClient) -> None:
    product = create_product(
        client,
        marketplace_product_id=None,
        product_url="https://www.amazon.in/dp/B000000001",
    )

    response = client.get(f"{BASE}/readiness")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ready"] is False
    assert body["issue_count"] == 1
    assert body["issues"] == [
        {
            "entity_type": "product",
            "entity_id": product["id"],
            "entity_name": product["name"],
            "code": "marketplace_product_id_missing",
            "message": "Marketplace product ID is required for collection.",
            "field": "marketplace_product_id",
        }
    ]


def test_collection_readiness_reports_competitor_product_missing_identity(
    client: TestClient,
) -> None:
    competitor = create_competitor(client)
    competitor_product = create_competitor_product(
        client,
        competitor["id"],
        marketplace_product_id=None,
        product_url="https://www.amazon.in/dp/B000000002",
    )

    response = client.get(f"{BASE}/readiness")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ready"] is False
    assert body["issue_count"] == 1
    assert body["issues"][0]["entity_type"] == "competitor_product"
    assert body["issues"][0]["entity_id"] == competitor_product["id"]
    assert body["issues"][0]["code"] == "marketplace_product_id_missing"
    assert body["issues"][0]["field"] == "marketplace_product_id"


def test_collection_readiness_reports_battle_card_without_usable_competitor_mapping(
    client: TestClient,
) -> None:
    competitor = create_competitor(client)
    product = create_product(client, product_url="https://www.amazon.in/dp/B000000001")
    competitor_product = create_competitor_product(
        client,
        competitor["id"],
        product_url="https://www.amazon.in/dp/B000000002",
    )
    battle_card = create_battle_card(
        client,
        product["id"],
        items=[{"competitor_product_id": competitor_product["id"]}],
    )
    archive = client.post(f"{BASE}/competitor-products/{competitor_product['id']}/archive")
    assert archive.status_code == 200

    response = client.get(f"{BASE}/readiness")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["counts"] == {
        "products_checked": 1,
        "competitor_products_checked": 0,
        "battle_cards_checked": 1,
        "battle_card_mappings_checked": 1,
    }
    assert {
        (issue["entity_type"], issue["entity_id"], issue["code"])
        for issue in body["issues"]
    } == {
        ("battle_card", battle_card["id"], "battle_card_no_usable_competitor_mappings"),
        (
            "battle_card_item",
            next(item["id"] for item in battle_card["items"]),
            "battle_card_mapping_competitor_product_not_ready",
        ),
    }


def test_collection_readiness_excludes_archived_owned_products_and_flags_inactive_competitors(
    client: TestClient,
) -> None:
    archived_product = create_product(
        client,
        product_url="https://www.amazon.in/dp/B000000001",
    )
    assert client.post(f"{BASE}/products/{archived_product['id']}/archive").status_code == 200

    competitor = create_competitor(client)
    competitor_product = create_competitor_product(
        client,
        competitor["id"],
        product_url="https://www.amazon.in/dp/B000000002",
    )
    assert client.post(f"{BASE}/competitors/{competitor['id']}/archive").status_code == 200

    response = client.get(f"{BASE}/readiness")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["counts"]["products_checked"] == 0
    assert body["counts"]["competitor_products_checked"] == 1
    assert body["issues"] == [
        {
            "entity_type": "competitor_product",
            "entity_id": competitor_product["id"],
            "entity_name": competitor_product["name"],
            "code": "competitor_archived",
            "message": "Competitor product is linked to an archived competitor.",
            "field": "competitor_id",
        }
    ]


def test_collection_readiness_response_totals_and_issue_order_are_deterministic(
    client: TestClient,
) -> None:
    ready_product = create_product(
        client,
        internal_sku="OWN-READY",
        marketplace_product_id="B000000009",
        product_url="https://www.amazon.in/dp/B000000009",
    )
    missing_identity_product = create_product(
        client,
        internal_sku="OWN-MISSING",
        marketplace_product_id=None,
        product_url="https://www.amazon.in/dp/B000000008",
    )
    battle_card = create_battle_card(client, ready_product["id"])

    first = client.get(f"{BASE}/readiness")
    second = client.get(f"{BASE}/readiness")

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert first.json()["counts"] == {
        "products_checked": 2,
        "competitor_products_checked": 0,
        "battle_cards_checked": 1,
        "battle_card_mappings_checked": 0,
    }
    assert [issue["code"] for issue in first.json()["issues"]] == [
        "battle_card_no_usable_competitor_mappings",
        "marketplace_product_id_missing",
    ]
    assert first.json()["issues"][1]["entity_id"] == missing_identity_product["id"]
    assert first.json()["issues"][0]["entity_id"] == battle_card["id"]
