from fastapi.testclient import TestClient
from novel_signal.main import app


def test_live_health() -> None:
    response = TestClient(app).get("/api/v1/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_all_module_boundaries_are_registered() -> None:
    client = TestClient(app)
    for path in (
        "universe", "keywords", "visibility", "ads", "listings", "commerce",
        "reviews", "market-share", "scorecards", "actions", "alerts", "collection",
    ):
        assert client.get(f"/api/v1/{path}/meta").status_code == 200


def test_all_required_week_one_sources_are_registered() -> None:
    response = TestClient(app).get("/api/v1/sources")
    assert response.status_code == 200
    sources = {item["source_type"] for item in response.json()}
    assert sources == {
        "amazon_sp_api",
        "amazon_ads_api",
        "amazon_brand_analytics",
        "google_search_console",
        "google_ads_api",
        "meta_marketing_api",
        "meta_ad_library",
        "amazon_public_pages",
    }
