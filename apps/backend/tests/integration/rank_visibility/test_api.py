from __future__ import annotations

import uuid

import pytest
from novel_signal.modules.rank_visibility.models import SerpCapture
from sqlalchemy import func, select

from .conftest import S3Context


def payload(context: S3Context, *, second: bool = False) -> dict[str, object]:
    if second:
        rows = [
            {
                "absolute_position": 1,
                "page_number": 1,
                "marketplace_product_id": "OWN1",
                "brand": "Novel",
                "placement_type": "organic",
                "displayed_price": 199,
                "rating": 4.5,
                "review_count": 100,
            },
            {
                "absolute_position": 2,
                "page_number": 1,
                "marketplace_product_id": "NEW1",
                "brand": "New Brand",
                "placement_type": "sponsored_brand_video",
                "badges": ["amazons_choice"],
            },
            {
                "absolute_position": 5,
                "page_number": 1,
                "marketplace_product_id": "COMP1",
                "brand": "Acme",
                "placement_type": "organic",
                "badges": ["deal"],
            },
        ]
    else:
        rows = [
            {
                "absolute_position": 1,
                "page_number": 1,
                "marketplace_product_id": "COMP1",
                "brand": "Acme",
                "placement_type": "sponsored_product",
                "badges": ["deal"],
            },
            {
                "absolute_position": 2,
                "page_number": 1,
                "marketplace_product_id": "OWN1",
                "brand": "Novel",
                "placement_type": "organic",
                "badges": ["best_seller"],
                "displayed_price": 209,
                "mrp": 249,
                "discount_percent": 16,
                "rating": 4.4,
                "review_count": 95,
            },
            {
                "absolute_position": 3,
                "page_number": 1,
                "marketplace_product_id": "UNKNOWN1",
                "brand": "Unknown Brand",
                "placement_type": "organic",
            },
            {
                "absolute_position": 25,
                "page_number": 2,
                "marketplace_product_id": "PAGE2",
                "brand": "Page Two",
                "placement_type": "editorial_or_deal",
            },
        ]
    return {
        "keyword_id": str(context.keyword.id),
        "marketplace": "amazon_in",
        "geo_code": "570023",
        "device_profile": "mobile" if second else "desktop",
        "captured_at": "2026-08-18T11:00:00Z" if second else "2026-08-18T10:00:00Z",
        "ingestion_key": "capture-2" if second else "capture-1",
        "parser_version": "normalizer-v1",
        "results": rows,
    }


def test_capture_ingestion_mapping_positions_filters_and_idempotency(s3: S3Context) -> None:
    assert s3.client.get("/api/v1/rank-visibility/meta").json() == {
        "module": "S3 Rank & Visibility",
        "status": "implemented",
    }
    response = s3.client.post("/api/v1/rank-visibility/captures", json=payload(s3))
    assert response.status_code == 201, response.text
    capture = response.json()
    assert capture["page_count"] == 2
    assert capture["result_count"] == 4
    assert [row["within_type_position"] for row in capture["results"]] == [1, 1, 2, 1]
    assert capture["results"][0]["competitor_product_id"] == str(s3.competitor_product.id)
    assert capture["results"][1]["product_id"] == str(s3.product.id)
    assert capture["results"][2]["marketplace_product_id"] == "UNKNOWN1"
    assert capture["results"][2]["product_id"] is None
    assert capture["results"][3]["page_number"] == 2
    detail = s3.client.get(f"/api/v1/rank-visibility/captures/{capture['id']}")
    assert detail.status_code == 200
    listing = s3.client.get(
        f"/api/v1/rank-visibility/captures?keyword_id={s3.keyword.id}&device_profile=desktop&limit=1"
    ).json()
    assert listing["total"] == 1
    assert listing["limit"] == 1
    duplicate = s3.client.post("/api/v1/rank-visibility/captures", json=payload(s3))
    assert duplicate.status_code == 409


def test_metrics_events_new_entrants_and_brand_presence(s3: S3Context) -> None:
    first = s3.client.post("/api/v1/rank-visibility/captures", json=payload(s3))
    second_payload = payload(s3, second=True)
    second_payload["device_profile"] = "desktop"
    second = s3.client.post("/api/v1/rank-visibility/captures", json=second_payload)
    assert first.status_code == second.status_code == 201
    common = f"keyword_id={s3.keyword.id}&marketplace_product_id=OWN1&device_profile=desktop"
    history = s3.client.get(f"/api/v1/rank-visibility/rank-history?{common}").json()
    assert [row["absolute_position"] for row in history["observations"]] == [2, 1]
    metrics = s3.client.get(f"/api/v1/rank-visibility/visibility?{common}").json()
    assert metrics == {
        "keyword_id": str(s3.keyword.id),
        "identity": "OWN1",
        "latest_rank": 1,
        "best_rank": 1,
        "latest_organic_rank": 1,
        "observation_count": 2,
        "rank_volatility": 1.0,
        "time_in_top_3_percent": 100.0,
        "time_in_top_10_percent": 100.0,
    }
    presence = s3.client.get(
        f"/api/v1/rank-visibility/brand-presence?capture_id={first.json()['id']}"
    ).json()
    assert presence["total_page_1_results"] == 3
    assert {row["brand"]: row["page_1_slot_count"] for row in presence["brands"]} == {
        "Acme": 1,
        "Novel": 1,
        "Unknown Brand": 1,
    }
    assert {row["page_1_share_percent"] for row in presence["brands"]} == {33.33}
    badges = s3.client.get("/api/v1/rank-visibility/badge-events?limit=100").json()
    changes = {
        (row["marketplace_product_id"], row["badge_type"], row["event_type"])
        for row in badges["items"]
    }
    assert ("OWN1", "best_seller", "acquired") in changes
    assert ("OWN1", "best_seller", "lost") in changes
    assert (
        len(
            [
                row
                for row in badges["items"]
                if row["marketplace_product_id"] == "COMP1" and row["badge_type"] == "deal"
            ]
        )
        == 1
    )
    entrants = s3.client.get("/api/v1/rank-visibility/new-entrants?limit=100").json()
    ids = [row["marketplace_product_id"] for row in entrants["items"]]
    assert ids.count("COMP1") == 1
    assert "NEW1" in ids


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("displayed_price", -1),
        ("mrp", -1),
        ("rating", 6),
        ("review_count", -1),
        ("page_number", 0),
        ("absolute_position", 0),
    ],
)
def test_invalid_result_values_rollback(s3: S3Context, field: str, value: int) -> None:
    body = payload(s3)
    body["ingestion_key"] = f"invalid-{field}"
    body["results"] = [{**body["results"][0], field: value}]  # type: ignore[index]
    before = s3.session.scalar(select(func.count()).select_from(SerpCapture))
    response = s3.client.post("/api/v1/rank-visibility/captures", json=body)
    assert response.status_code == 422
    s3.session.expire_all()
    assert s3.session.scalar(select(func.count()).select_from(SerpCapture)) == before


def test_identity_validation_duplicate_positions_and_not_found(s3: S3Context) -> None:
    conflict = s3.client.get(
        f"/api/v1/rank-visibility/rank-history?keyword_id={s3.keyword.id}"
        "&product_id=00000000-0000-0000-0000-000000000001&marketplace_product_id=OWN1"
    )
    assert conflict.status_code == 422
    duplicate = payload(s3)
    duplicate["results"] = [duplicate["results"][0], duplicate["results"][0]]  # type: ignore[index]
    assert s3.client.post("/api/v1/rank-visibility/captures", json=duplicate).status_code == 422
    assert s3.client.get(f"/api/v1/rank-visibility/captures/{uuid.uuid4()}").status_code == 404
