from typing import Any

import pytest
from fastapi.testclient import TestClient

from .test_api import BASE, create_keyword, create_s1_targets


def test_keyword_csv_dry_run_import_export_and_zero_write(client: TestClient) -> None:
    header = (
        "keyword_text,marketplace,category,tier,tracking_status,intent_cluster,"
        "sources,volume_estimate,seasonality_index,notes\n"
    )
    valid = (
        header + "overnight diaper,amazon_in,Baby Care,T1,active,problem_benefit,"
        "manual|review_mining,100,2,validated\n"
    )
    dry = client.post(f"{BASE}/csv/keywords/dry-run", json={"csv_text": valid})
    assert dry.json()["valid"] is True and client.get(BASE).json()["total"] == 0
    imported = client.post(f"{BASE}/csv/keywords/import", json={"csv_text": valid})
    assert imported.json()["imported_rows"] == 1
    enrichment = (
        header + "overnight diaper,amazon_in,Baby Care,T1,active,problem_benefit,"
        "brand_analytics,100,2,validated\n"
    )
    assert client.post(f"{BASE}/csv/keywords/dry-run", json={"csv_text": enrichment}).json()[
        "valid"
    ]
    assert (
        client.post(f"{BASE}/csv/keywords/import", json={"csv_text": enrichment}).json()[
            "imported_rows"
        ]
        == 1
    )
    enriched = client.get(BASE, params={"search": "overnight diaper"}).json()["items"][0]
    assert {source["source_type"] for source in enriched["sources"]} == {
        "manual",
        "review_mining",
        "brand_analytics",
    }
    assert client.get(BASE).json()["total"] == 1
    duplicate = client.post(f"{BASE}/csv/keywords/dry-run", json={"csv_text": enrichment}).json()
    assert duplicate["valid"] is False and duplicate["errors"][0]["field"] == "sources"
    exported = client.get(f"{BASE}/csv/keywords/export")
    assert "overnight diaper" in exported.text
    assert client.get(f"{BASE}/csv/keywords/template").status_code == 200
    invalid = (
        header
        + " Baby   Diapers ,amazon_in,Baby Care,T1,active,generic_category,manual,,,\n"
        + "baby diapers,amazon_in,Baby Care,T1,active,generic_category,manual,,,\n"
        + "invalid tier,amazon_in,Baby Care,BAD,active,generic_category,manual,,,\n"
    )
    before = client.get(BASE).json()["total"]
    result = client.post(f"{BASE}/csv/keywords/dry-run", json={"csv_text": invalid}).json()
    assert result["valid"] is False and result["invalid_rows"] == 2
    assert client.post(f"{BASE}/csv/keywords/import", json={"csv_text": invalid}).status_code == 422
    assert client.get(BASE).json()["total"] == before


def test_tracking_target_csv_reference_duplicate_and_round_trip(client: TestClient) -> None:
    keyword = create_keyword(client)
    product, _ = create_s1_targets(client)
    header = "keyword_id,product_id,competitor_product_id,cadence_minutes,enabled\n"
    valid = header + f"{keyword['id']},{product['id']},,240,true\n"
    assert (
        client.post(f"{BASE}/csv/tracking-targets/dry-run", json={"csv_text": valid}).json()[
            "valid"
        ]
        is True
    )
    assert (
        client.post(f"{BASE}/csv/tracking-targets/import", json={"csv_text": valid}).json()[
            "imported_rows"
        ]
        == 1
    )
    exported = client.get(f"{BASE}/csv/tracking-targets/export")
    assert product["id"] in exported.text
    duplicate_file = (
        header
        + f"{keyword['id']},{product['id']},,240,true\n{keyword['id']},{product['id']},,240,true\n"
    )
    result = client.post(
        f"{BASE}/csv/tracking-targets/dry-run", json={"csv_text": duplicate_file}
    ).json()
    assert result["valid"] is False
    missing = (
        header
        + "00000000-0000-4000-8000-000000000000,00000000-0000-4000-8000-000000000001,,240,true\n"
    )
    assert (
        client.post(f"{BASE}/csv/tracking-targets/import", json={"csv_text": missing}).status_code
        == 422
    )


def test_csv_transaction_rolls_back_on_commit_failure(client: TestClient, monkeypatch: Any) -> None:
    from novel_signal.modules.keywords.csv_service import KeywordCsvService

    header = (
        "keyword_text,marketplace,category,tier,tracking_status,intent_cluster,"
        "sources,volume_estimate,seasonality_index,notes\n"
    )
    data = header + "rollback keyword,amazon_in,,T1,active,unclassified,manual,,,\n"
    original = KeywordCsvService.import_rows

    def failing(self: KeywordCsvService, entity: Any, text: str) -> Any:
        result, rows = self.validate(entity, text)
        assert result.valid
        from novel_signal.modules.keywords.models import Keyword
        from novel_signal.modules.keywords.schemas import normalize_keyword

        payload = rows[0]
        self.session.add(
            Keyword(
                **payload.model_dump(exclude={"sources"}),
                normalized_text=normalize_keyword(payload.keyword_text),
            )
        )
        self.session.flush()
        self.session.rollback()
        raise RuntimeError("simulated")

    monkeypatch.setattr(KeywordCsvService, "import_rows", failing)
    try:
        with pytest.raises(RuntimeError):
            client.post(f"{BASE}/csv/keywords/import", json={"csv_text": data})
    finally:
        monkeypatch.setattr(KeywordCsvService, "import_rows", original)
    assert client.get(BASE, params={"search": "rollback keyword"}).json()["total"] == 0
