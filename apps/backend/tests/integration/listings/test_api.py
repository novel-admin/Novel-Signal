from __future__ import annotations

import uuid

from novel_signal.modules.actions.models import ChangeEvent
from sqlalchemy import select

from .conftest import Context


def body(identity: str, key: str, time: str, **changes: object) -> dict[str, object]:
    data = {
        "marketplace": "amazon_in",
        "marketplace_product_id": identity,
        "captured_at": time,
        "ingestion_key": key,
        "parser_version": "product-detail-v1",
        "source_url": f"https://amazon.in/dp/{identity}",
        "title": "  Soft   Baby Wipes ",
        "brand": "Novel" if identity == "OWN1" else "Acme",
        "category_path": "Baby > Wipes",
        "bullets": ["Soft care", "Pure water", "Dermatologically tested"],
        "description": "Gentle daily care",
        "a_plus_present": False,
        "image_urls": ["https://img/1", "https://img/2"],
        "video_present": False,
        "variation_count": None,
    }
    data.update(changes)
    return data


def test_ingestion_mapping_baseline_latest_history_and_idempotency(s5: Context) -> None:
    assert s5.client.get("/api/v1/listing-intelligence/meta").json() == {
        "module": "S5 Listing Intelligence",
        "status": "implemented",
    }
    created = s5.client.post(
        "/api/v1/listing-intelligence/snapshots", json=body("OWN1", "one", "2026-08-18T10:00:00Z")
    )
    assert created.status_code == 201, created.text
    value = created.json()
    assert value["product_id"] == str(s5.product.id)
    assert value["title"] == "Soft Baby Wipes"
    assert value["image_count"] == 2
    assert value["completeness_score"] == 50
    assert (
        s5.client.get(f"/api/v1/listing-intelligence/latest?product_id={s5.product.id}").status_code
        == 200
    )
    assert (
        s5.client.get(f"/api/v1/listing-intelligence/history?product_id={s5.product.id}").json()[
            "total"
        ]
        == 1
    )
    assert s5.client.get("/api/v1/listing-intelligence/changes").json()["total"] == 0
    assert (
        s5.client.post(
            "/api/v1/listing-intelligence/snapshots",
            json=body("OWN1", "one", "2026-08-18T10:00:00Z"),
        ).status_code
        == 409
    )
    unknown = s5.client.post(
        "/api/v1/listing-intelligence/snapshots",
        json=body("UNKNOWN", "unknown", "2026-08-18T10:00:00Z"),
    )
    assert unknown.status_code == 201
    assert unknown.json()["product_id"] is None


def test_changes_normalization_completeness_comparison_and_filters(s5: Context) -> None:
    s5.client.post(
        "/api/v1/listing-intelligence/snapshots", json=body("OWN1", "base", "2026-08-18T10:00:00Z")
    )
    comp = body(
        "COMP1",
        "comp",
        "2026-08-18T10:00:00Z",
        a_plus_present=True,
        image_urls=[f"https://img/{i}" for i in range(5)],
        video_present=True,
        video_count=1,
        variation_count=3,
    )
    assert s5.client.post("/api/v1/listing-intelligence/snapshots", json=comp).json()[
        "competitor_product_id"
    ] == str(s5.competitor_product.id)
    compare = s5.client.get(
        f"/api/v1/listing-intelligence/comparison?product_id={s5.product.id}&competitor_product_id={s5.competitor_product.id}"
    ).json()
    assert compare["deltas"]["score_difference"] == -50
    assert {
        "owned_missing_a_plus",
        "owned_has_fewer_images",
        "owned_missing_video",
        "owned_lower_completeness",
    }.issubset(compare["gaps"])
    second = body(
        "OWN1",
        "second",
        "2026-08-18T11:00:00Z",
        title="Soft Baby Wipes Plus",
        description=None,
        a_plus_present=True,
        a_plus_sections=[{"heading": "Care"}],
        image_urls=[f"https://img/{i}" for i in range(2, 7)],
        video_present=True,
        video_count=1,
        variation_count=2,
    )
    result = s5.client.post("/api/v1/listing-intelligence/snapshots", json=second)
    assert result.status_code == 201
    assert result.json()["completeness_score"] == 90
    changes = s5.client.get(
        f"/api/v1/listing-intelligence/changes?product_id={s5.product.id}&limit=100"
    ).json()
    fields = {x["field_name"] for x in changes["items"]}
    assert {
        "title",
        "description",
        "a_plus_present",
        "image_added",
        "image_removed",
        "image_count",
        "video_present",
        "variation_count",
    }.issubset(fields)
    s5.session.expire_all()
    title_event = next(
        item
        for item in s5.session.scalars(select(ChangeEvent)).all()
        if item.field_name == "title"
    )
    assert title_event.target_type == "product"
    assert title_event.old_observation_type == "listing_snapshot"
    assert title_event.new_observation_type == "listing_snapshot"
    assert title_event.old_value == "Soft Baby Wipes"
    assert title_event.new_value == "Soft Baby Wipes Plus"
    score = s5.client.get(
        f"/api/v1/listing-intelligence/completeness?product_id={s5.product.id}"
    ).json()
    assert score["score"] == 90
    assert "description" in score["missing_components"]
    whitespace = body(
        "OWN1",
        "third",
        "2026-08-18T12:00:00Z",
        title="  Soft   Baby Wipes Plus ",
        description=None,
        a_plus_present=True,
        a_plus_sections=[{"heading": "Care"}],
        image_urls=[f"https://img/{i}" for i in range(2, 7)],
        video_present=True,
        video_count=1,
        variation_count=2,
    )
    s5.client.post("/api/v1/listing-intelligence/snapshots", json=whitespace)
    title_changes = s5.client.get(
        f"/api/v1/listing-intelligence/changes?product_id={s5.product.id}&field_name=title"
    ).json()
    assert title_changes["total"] == 1


def test_validation_and_not_found(s5: Context) -> None:
    invalid = body("OWN1", "invalid", "2026-08-18T10:00:00Z", variation_count=-1)
    assert s5.client.post("/api/v1/listing-intelligence/snapshots", json=invalid).status_code == 422
    assert (
        s5.client.get(f"/api/v1/listing-intelligence/snapshots/{uuid.uuid4()}").status_code == 404
    )
    assert (
        s5.client.get(
            f"/api/v1/listing-intelligence/latest?product_id={s5.product.id}&marketplace_product_id=OWN1"
        ).status_code
        == 422
    )
