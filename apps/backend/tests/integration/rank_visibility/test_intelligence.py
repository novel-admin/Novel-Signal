from __future__ import annotations

from novel_signal.modules.keywords.models import IntentCluster, Keyword, KeywordTrackingStatus
from novel_signal.modules.universe.models import Marketplace, TrackingTier

from .conftest import S3Context


def _capture(
    s3: S3Context,
    *,
    keyword: Keyword,
    key: str,
    captured_at: str,
    rows: list[dict[str, object]],
) -> dict[str, object]:
    response = s3.client.post(
        "/api/v1/rank-visibility/captures",
        json={
            "keyword_id": str(keyword.id),
            "marketplace": "amazon_in",
            "geo_code": "570023",
            "device_profile": "desktop",
            "captured_at": captured_at,
            "source_job_id": f"job-{key}",
            "parser_version": "amazon-serp-v1",
            "ingestion_key": key,
            "results": rows,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _row(position: int, asin: str, placement: str, brand: str) -> dict[str, object]:
    return {
        "absolute_position": position,
        "page_number": 1,
        "marketplace_product_id": asin,
        "placement_type": placement,
        "brand": brand,
    }


def test_reverse_asin_summarizes_keywords_history_and_latest_lineage(s3: S3Context) -> None:
    other = Keyword(
        keyword_text="gentle wipes",
        normalized_text="gentle wipes",
        marketplace=Marketplace.AMAZON_IN,
        tier=TrackingTier.T1,
        tracking_status=KeywordTrackingStatus.ACTIVE,
        intent_cluster=IntentCluster.GENERIC_CATEGORY,
    )
    s3.session.add(other)
    s3.session.commit()
    _capture(
        s3,
        keyword=s3.keyword,
        key="reverse-old",
        captured_at="2026-08-20T10:00:00Z",
        rows=[_row(5, "OWN1", "organic", "Novel")],
    )
    latest = _capture(
        s3,
        keyword=s3.keyword,
        key="reverse-latest",
        captured_at="2026-08-20T11:00:00Z",
        rows=[
            _row(1, "OWN1", "sponsored_product", "Novel"),
            _row(4, "OWN1", "organic", "Novel"),
        ],
    )
    _capture(
        s3,
        keyword=other,
        key="reverse-other",
        captured_at="2026-08-20T12:00:00Z",
        rows=[_row(3, "OWN1", "organic", "Novel")],
    )

    response = s3.client.get(f"/api/v1/rank-visibility/reverse-asin?product_id={s3.product.id}")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["keyword_count"] == 2
    assert body["context_count"] == 2
    baby = next(row for row in body["keywords"] if row["keyword_text"] == "baby wipes")
    assert baby["latest_position"] == 1
    assert baby["latest_organic_position"] == 1
    assert baby["sponsored_present"] is True
    assert baby["first_observed_at"].startswith("2026-08-20T10:00:00")
    assert baby["latest_capture_id"] == latest["id"]
    assert len(baby["latest_result_ids"]) == 2
    assert baby["source_job_id"] == "job-reverse-latest"


def test_reverse_asin_absent_identity_returns_no_fabricated_observations(s3: S3Context) -> None:
    response = s3.client.get("/api/v1/rank-visibility/reverse-asin?marketplace_product_id=ABSENT")
    assert response.status_code == 200
    assert response.json() == {
        "identity": "ABSENT",
        "keyword_count": 0,
        "context_count": 0,
        "keywords": [],
    }


def test_amazon_share_of_voice_uses_explicit_organic_paid_slot_denominators(
    s3: S3Context,
) -> None:
    capture = _capture(
        s3,
        keyword=s3.keyword,
        key="sov",
        captured_at="2026-08-21T10:00:00Z",
        rows=[
            _row(1, "OWN1", "sponsored_product", "Novel"),
            _row(2, "COMP1", "sponsored_brand", "Acme"),
            _row(3, "OWN1", "organic", "Novel"),
            _row(4, "OTHER", "organic", "Other"),
            _row(5, "DEAL", "editorial_or_deal", "Novel"),
        ],
    )
    response = s3.client.get(
        f"/api/v1/rank-visibility/amazon-share-of-voice?capture_id={capture['id']}&brand=Novel"
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["organic"] == {
        "matched_slots": 1,
        "eligible_slots": 2,
        "share_percent": 50.0,
    }
    assert body["paid"] == {
        "matched_slots": 1,
        "eligible_slots": 2,
        "share_percent": 50.0,
    }
    assert body["total"] == {
        "matched_slots": 2,
        "eligible_slots": 4,
        "share_percent": 50.0,
    }
    assert len(body["matched_result_ids"]) == 2
    assert body["source_job_id"] == "job-sov"


def test_keyword_gaps_use_latest_capture_per_keyword_geo_device_context(s3: S3Context) -> None:
    _capture(
        s3,
        keyword=s3.keyword,
        key="gap-old",
        captured_at="2026-08-22T10:00:00Z",
        rows=[_row(1, "COMP1", "organic", "Acme")],
    )
    latest = _capture(
        s3,
        keyword=s3.keyword,
        key="gap-latest",
        captured_at="2026-08-22T11:00:00Z",
        rows=[
            _row(1, "OWN1", "organic", "Novel"),
            _row(2, "COMP1", "organic", "Acme"),
            _row(3, "COMP1", "sponsored_product", "Acme"),
        ],
    )
    response = s3.client.get(
        "/api/v1/rank-visibility/keyword-gaps"
        f"?owned_product_id={s3.product.id}"
        f"&competitor_product_id={s3.competitor_product.id}"
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["contexts_checked"] == 1
    assert body["gap_count"] == 1
    assert body["gaps"][0]["capture_id"] == latest["id"]
    assert body["gaps"][0]["gap_types"] == ["owned_paid_gap"]
    assert body["gaps"][0]["owned_organic_present"] is True
    assert body["gaps"][0]["competitor_paid_present"] is True
    assert len(body["gaps"][0]["competitor_result_ids"]) == 2


def test_intelligence_identity_validation_is_explicit(s3: S3Context) -> None:
    reverse = s3.client.get("/api/v1/rank-visibility/reverse-asin")
    assert reverse.status_code == 422
    sov = s3.client.get(
        "/api/v1/rank-visibility/amazon-share-of-voice"
        f"?capture_id=00000000-0000-0000-0000-000000000001&brand=Novel&product_id={s3.product.id}"
    )
    assert sov.status_code == 422
