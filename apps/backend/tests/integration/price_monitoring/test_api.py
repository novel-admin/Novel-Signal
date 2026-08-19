from datetime import UTC, datetime, timedelta
from decimal import Decimal

from .conftest import Context

BASE = datetime.now(UTC) - timedelta(minutes=10)


def payload(
    identity: str = "OWN-S6",
    *,
    at: datetime = BASE,
    price: str | None = "499",
    geo: str = "560001",
    key: str = "s6-1",
) -> dict[str, object]:
    return {
        "marketplace": "amazon_in",
        "marketplace_product_id": identity,
        "observed_at": at.isoformat(),
        "geo_code": geo,
        "currency": "inr",
        "availability_status": "available",
        "primary_price": price,
        "mrp": "599",
        "shipping_amount": "40",
        "coupon_text": "₹50 applied",
        "coupon_value": "50",
        "coupon_type": "absolute",
        "primary_seller_name": "Seller A",
        "is_featured_offer": True,
        "offers": [
            {
                "seller_name": "Seller A",
                "seller_id": "A",
                "offer_price": price,
                "shipping_amount": "40",
                "coupon_value": "50",
                "availability_status": "available",
                "is_featured_offer": True,
            },
            {
                "seller_name": "Seller B",
                "seller_id": "B",
                "offer_price": "510",
                "availability_status": "available",
            },
        ],
        "source_job_id": None,
        "parser_version": "qa-1",
        "provider": "normalized-test",
        "ingestion_key": key,
    }


def test_meta_ingestion_mapping_money_offers_and_idempotency(s6: Context) -> None:
    assert s6.client.get("/api/v1/price-monitoring/meta").json() == {
        "module": "S6 Price Monitoring",
        "status": "implemented",
    }
    response = s6.client.post("/api/v1/price-monitoring/observations", json=payload())
    assert response.status_code == 201
    item = response.json()
    assert item["product_id"] == str(s6.product.id) and item["competitor_product_id"] is None
    assert Decimal(item["primary_price"]) == Decimal("499.00")
    assert Decimal(item["discount_percent"]) == Decimal("16.69")
    assert Decimal(item["effective_price"]) == Decimal("489.00")
    assert item["seller_count"] == 2 and len(item["offers"]) == 2
    assert item["offers"][0]["is_featured_offer"] is True
    assert (
        s6.client.get(f"/api/v1/price-monitoring/observations/{item['id']}/offers").status_code
        == 200
    )
    assert (
        s6.client.post("/api/v1/price-monitoring/observations", json=payload()).status_code == 409
    )


def test_unknown_unavailable_null_and_validation(s6: Context) -> None:
    unavailable = payload("UNKNOWN-S6", price=None, key="unknown")
    unavailable.update(
        {
            "availability_status": "unavailable",
            "mrp": None,
            "shipping_amount": None,
            "coupon_value": None,
            "coupon_type": None,
            "offers": [],
        }
    )
    item = s6.client.post("/api/v1/price-monitoring/observations", json=unavailable).json()
    assert item["product_id"] is None and item["competitor_product_id"] is None
    assert item["primary_price"] is None and item["effective_price"] is None
    invalid = payload(key="bad")
    invalid["primary_price"] = "-1"
    assert s6.client.post("/api/v1/price-monitoring/observations", json=invalid).status_code == 422
    invalid = payload(key="bad2")
    invalid["discount_percent"] = "101"
    assert s6.client.post("/api/v1/price-monitoring/observations", json=invalid).status_code == 422
    invalid = payload(key="bad3")
    invalid["seller_count"] = 3
    assert s6.client.post("/api/v1/price-monitoring/observations", json=invalid).status_code == 422


def test_events_geo_history_latest_metrics_and_freshness(s6: Context) -> None:
    assert (
        s6.client.post("/api/v1/price-monitoring/observations", json=payload()).status_code == 201
    )
    second = payload(at=BASE + timedelta(minutes=1), price="449", key="s6-2")
    assert s6.client.post("/api/v1/price-monitoring/observations", json=second).status_code == 201
    other_geo = payload(at=BASE + timedelta(minutes=2), price="600", geo="570001", key="s6-geo")
    assert (
        s6.client.post("/api/v1/price-monitoring/observations", json=other_geo).status_code == 201
    )
    events = s6.client.get(
        "/api/v1/price-monitoring/events", params={"product_id": str(s6.product.id)}
    ).json()
    assert events["total"] == 1
    assert events["items"][0]["event_type"] == "price_decrease"
    assert Decimal(events["items"][0]["absolute_change"]) == Decimal("-50.00")
    assert Decimal(events["items"][0]["percent_change"]) == Decimal("-10.02")
    latest = s6.client.get(
        "/api/v1/price-monitoring/latest",
        params={"product_id": str(s6.product.id), "geo_code": "560001"},
    ).json()
    assert Decimal(latest["observation"]["primary_price"]) == Decimal("449.00")
    assert latest["freshness"]["freshness_status"] == "fresh"
    history = s6.client.get(
        "/api/v1/price-monitoring/history",
        params={"product_id": str(s6.product.id), "geo_code": "560001"},
    ).json()
    assert [Decimal(x["primary_price"]) for x in history["items"]] == [
        Decimal("499.00"),
        Decimal("449.00"),
    ]
    metrics = s6.client.get(
        "/api/v1/price-monitoring/metrics",
        params={"product_id": str(s6.product.id), "geo_code": "560001"},
    ).json()
    assert Decimal(metrics["minimum_price"]) == Decimal("449.00")
    assert Decimal(metrics["maximum_price"]) == Decimal("499.00")
    assert (
        Decimal(metrics["average_price"]) == Decimal("474.00") and metrics["observation_count"] == 2
    )


def test_availability_events_and_comparison(s6: Context) -> None:
    s6.client.post("/api/v1/price-monitoring/observations", json=payload())
    unavailable = payload(at=BASE + timedelta(minutes=1), price=None, key="off")
    unavailable.update(
        {
            "availability_status": "unavailable",
            "mrp": None,
            "shipping_amount": None,
            "coupon_value": None,
            "coupon_type": None,
            "offers": [],
        }
    )
    s6.client.post("/api/v1/price-monitoring/observations", json=unavailable)
    back = payload(at=BASE + timedelta(minutes=2), price="479", key="back")
    s6.client.post("/api/v1/price-monitoring/observations", json=back)
    competitor = payload("COMP-S6", at=BASE + timedelta(minutes=2), price="529", key="comp")
    result = s6.client.post("/api/v1/price-monitoring/observations", json=competitor).json()
    assert result["competitor_product_id"] == str(s6.competitor_product.id)
    events = s6.client.get(
        "/api/v1/price-monitoring/events", params={"product_id": str(s6.product.id)}
    ).json()["items"]
    assert {x["event_type"] for x in events} >= {"became_unavailable", "became_available"}
    comparison = s6.client.get(
        "/api/v1/price-monitoring/comparison",
        params={
            "product_id": str(s6.product.id),
            "competitor_product_id": str(s6.competitor_product.id),
            "geo_code": "560001",
        },
    ).json()
    assert "owned_cheaper" in comparison["signals"]
    assert Decimal(comparison["deltas"]["primary_price_difference"]) == Decimal("-50.00")
    assert comparison["deltas"]["seller_count_difference"] == 0


def test_errors_uncertain_coupon_and_filters(s6: Context) -> None:
    uncertain = payload(key="uncertain")
    uncertain.update(
        {
            "coupon_text": "up to ₹100",
            "coupon_value": None,
            "coupon_type": "uncertain",
            "shipping_amount": None,
        }
    )
    item = s6.client.post("/api/v1/price-monitoring/observations", json=uncertain).json()
    assert Decimal(item["effective_price"]) == Decimal("499.00")
    assert s6.client.get("/api/v1/price-monitoring/latest").status_code == 422
    assert (
        s6.client.get(
            "/api/v1/price-monitoring/latest",
            params={"product_id": str(s6.product.id), "marketplace_product_id": "OWN-S6"},
        ).status_code
        == 422
    )
    assert (
        s6.client.get(
            "/api/v1/price-monitoring/observations/00000000-0000-0000-0000-000000000000"
        ).status_code
        == 404
    )
    assert (
        s6.client.get(
            "/api/v1/price-monitoring/history",
            params={
                "product_id": str(s6.product.id),
                "from": "2026-02-02T00:00:00Z",
                "to": "2026-01-01T00:00:00Z",
            },
        ).status_code
        == 422
    )
    listed = s6.client.get(
        "/api/v1/price-monitoring/observations",
        params={"marketplace_product_id": "OWN-S6", "geo_code": "560001", "limit": 1},
    ).json()
    assert listed["total"] == 1 and len(listed["items"]) == 1


def test_increase_staleness_same_and_more_expensive_signals(s6: Context) -> None:
    old_at = datetime.now(UTC) - timedelta(hours=6)
    s6.client.post(
        "/api/v1/price-monitoring/observations",
        json=payload(at=old_at, price="499", key="stale-own"),
    )
    s6.client.post(
        "/api/v1/price-monitoring/observations",
        json=payload("COMP-S6", at=old_at, price="499", key="stale-comp"),
    )
    comparison = s6.client.get(
        "/api/v1/price-monitoring/comparison",
        params={
            "product_id": str(s6.product.id),
            "competitor_product_id": str(s6.competitor_product.id),
            "geo_code": "560001",
        },
    ).json()
    assert {"same_price", "owned_stale", "competitor_stale"} <= set(comparison["signals"])
    increased = payload(at=old_at + timedelta(minutes=1), price="550", key="increase")
    assert (
        s6.client.post("/api/v1/price-monitoring/observations", json=increased).status_code == 201
    )
    comparison = s6.client.get(
        "/api/v1/price-monitoring/comparison",
        params={
            "product_id": str(s6.product.id),
            "competitor_product_id": str(s6.competitor_product.id),
            "geo_code": "560001",
        },
    ).json()
    assert "owned_more_expensive" in comparison["signals"]
    events = s6.client.get(
        "/api/v1/price-monitoring/events",
        params={"product_id": str(s6.product.id)},
    ).json()["items"]
    assert events[0]["event_type"] == "price_increase"
