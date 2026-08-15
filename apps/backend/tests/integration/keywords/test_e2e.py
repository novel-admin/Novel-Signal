from fastapi.testclient import TestClient

from .test_api import BASE, create_s1_targets, keyword_payload


def test_complete_keyword_configuration_workflow(client: TestClient) -> None:
    created = client.post(
        BASE,
        json=keyword_payload(
            "sensitive baby wipes",
            sources=[
                {"source_type": "manual"},
                {"source_type": "autocomplete"},
                {"source_type": "amazon_ads", "source_reference": "campaign-42"},
            ],
        ),
    )
    assert created.status_code == 201
    keyword = created.json()
    assert len(keyword["sources"]) == 3
    assert client.post(BASE, json=keyword_payload(" Sensitive  Baby Wipes ")).status_code == 409

    product, competitor_product = create_s1_targets(client)
    owned_target = client.post(
        f"{BASE}/tracking-targets",
        json={"keyword_id": keyword["id"], "product_id": product["id"]},
    )
    assert owned_target.status_code == 201
    assert owned_target.json()["cadence_minutes"] == 240
    competitor_target = client.post(
        f"{BASE}/tracking-targets",
        json={
            "keyword_id": keyword["id"],
            "competitor_product_id": competitor_product["id"],
            "cadence_minutes": 360,
        },
    )
    assert competitor_target.status_code == 201

    assert client.get(BASE, params={"priority_only": True}).json()["total"] == 1
    assert (
        client.patch(f"{BASE}/{keyword['id']}", json={"tracking_status": "paused"}).status_code
        == 200
    )
    assert client.get(BASE, params={"priority_only": True}).json()["total"] == 0
    assert (
        client.patch(f"{BASE}/{keyword['id']}", json={"tracking_status": "active"}).status_code
        == 200
    )

    assert client.post(f"{BASE}/{keyword['id']}/archive").status_code == 200
    assert client.post(f"{BASE}/{keyword['id']}/restore").status_code == 200

    header = (
        "keyword_text,marketplace,category,tier,tracking_status,intent_cluster,"
        "sources,volume_estimate,seasonality_index,notes\n"
    )
    csv_text = (
        header + "overnight wetness protection,amazon_in,Baby Care,T2,active,problem_benefit,"
        "review_mining,,,workflow import\n"
    )
    dry_run = client.post(f"{BASE}/csv/keywords/dry-run", json={"csv_text": csv_text})
    assert dry_run.status_code == 200 and dry_run.json()["valid"]
    imported = client.post(f"{BASE}/csv/keywords/import", json={"csv_text": csv_text})
    assert imported.status_code == 200 and imported.json()["imported_rows"] == 1
    assert "overnight wetness protection" in client.get(f"{BASE}/csv/keywords/export").text

    keyword_read = client.get(f"{BASE}/{keyword['id']}")
    assert keyword_read.status_code == 200 and len(keyword_read.json()["sources"]) == 3
    targets = client.get(f"{BASE}/tracking-targets", params={"keyword_id": keyword["id"]})
    assert targets.status_code == 200 and targets.json()["total"] == 2
