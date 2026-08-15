import csv
import io
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from novel_signal.db import Base, get_db
from novel_signal.main import app
from novel_signal.modules.universe.csv_service import UniverseCsvService
from novel_signal.modules.universe.models import Competitor
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

BASE = "/api/v1/universe"


def sqlite_engine():  # type: ignore[no-untyped-def]
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
    return engine


@pytest.fixture
def csv_client() -> Iterator[TestClient]:
    engine = sqlite_engine()

    def override_db() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()


def make_csv(columns: list[str], rows: list[list[str]]) -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(columns)
    writer.writerows(rows)
    return output.getvalue()


COMPETITOR_COLUMNS = [
    "name",
    "parent_company",
    "amazon_store_url",
    "amazon_seller_id",
    "category_presence",
    "positioning_tier",
    "threat_rating",
    "analyst_owner",
    "notes",
]


def competitor_csv(*rows: list[str]) -> str:
    return make_csv(COMPETITOR_COLUMNS, list(rows))


def test_valid_dry_run_transactional_import_export_and_database_conflict(
    csv_client: TestClient,
) -> None:
    content = competitor_csv(
        [
            "CSV Competitor",
            "CSV Parent",
            "",
            "",
            "Baby Care",
            "mid",
            "4",
            "CSV Analyst",
            "Imported configuration",
        ]
    )
    dry_run = csv_client.post(f"{BASE}/csv/competitors/dry-run", json={"csv_text": content})
    assert dry_run.status_code == 200
    assert dry_run.json() == {
        "valid": True,
        "total_rows": 1,
        "valid_rows": 1,
        "invalid_rows": 0,
        "errors": [],
    }
    assert csv_client.get(f"{BASE}/competitors").json()["total"] == 0

    imported = csv_client.post(f"{BASE}/csv/competitors/import", json={"csv_text": content})
    assert imported.status_code == 200
    assert imported.json() == {"imported_rows": 1, "entity": "competitors"}
    assert csv_client.get(f"{BASE}/competitors").json()["total"] == 1

    exported = csv_client.get(f"{BASE}/csv/competitors/export")
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("text/csv")
    assert "CSV Competitor" in exported.text
    assert exported.text.splitlines()[0] == ",".join(COMPETITOR_COLUMNS)
    conflict = csv_client.post(
        f"{BASE}/csv/competitors/dry-run", json={"csv_text": exported.text}
    ).json()
    assert not conflict["valid"]
    assert {error["code"] for error in conflict["errors"]} & {"id_conflict", "database_conflict"}


def test_invalid_dry_run_reports_rows_and_actual_import_writes_nothing(
    csv_client: TestClient,
) -> None:
    content = competitor_csv(
        ["Valid Row", "", "", "", "Baby Care", "mid", "3", "", ""],
        ["", "", "", "", "Baby Care", "invalid-tier", "9", "", ""],
    )
    result = csv_client.post(f"{BASE}/csv/competitors/dry-run", json={"csv_text": content}).json()
    assert result["valid"] is False
    assert result["total_rows"] == 2
    assert result["valid_rows"] == 1
    assert result["invalid_rows"] == 1
    assert {error["field"] for error in result["errors"]} >= {
        "name",
        "positioning_tier",
        "threat_rating",
    }
    imported = csv_client.post(f"{BASE}/csv/competitors/import", json={"csv_text": content})
    assert imported.status_code == 422
    assert imported.json()["detail"]["code"] == "csv_validation_failed"
    assert csv_client.get(f"{BASE}/competitors").json()["total"] == 0


def test_duplicate_csv_rows_are_rejected(csv_client: TestClient) -> None:
    row = ["Duplicate", "", "", "", "Baby Care", "mid", "3", "", ""]
    result = csv_client.post(
        f"{BASE}/csv/competitors/dry-run", json={"csv_text": competitor_csv(row, row)}
    ).json()
    assert not result["valid"]
    assert any(
        error["code"] == "duplicate_csv_row" and error["row"] == 3 for error in result["errors"]
    )


def test_product_csv_rejects_bad_asin_and_enum(csv_client: TestClient) -> None:
    template = csv_client.get(f"{BASE}/csv/products/template").text
    template_rows = list(csv.reader(io.StringIO(template)))
    columns = template_rows[0]
    bad_asin = template_rows[1].copy()
    bad_enum = template_rows[1].copy()
    bad_enum[columns.index("internal_sku")] = "SAMPLE-SKU-002"
    bad_enum[columns.index("marketplace_product_id")] = "B0SAMPLE03"
    bad_asin[columns.index("marketplace_product_id")] = "BAD-ASIN"
    bad_enum[columns.index("tracking_tier")] = "T9"
    result = csv_client.post(
        f"{BASE}/csv/products/dry-run",
        json={"csv_text": make_csv(columns, [bad_asin, bad_enum])},
    ).json()
    assert not result["valid"]
    fields = {error["field"] for error in result["errors"]}
    assert "marketplace_product_id" in fields
    assert "tracking_tier" in fields


def test_foreign_key_validation_and_all_templates_exports(csv_client: TestClient) -> None:
    for entity in (
        "competitors",
        "products",
        "competitor-products",
        "battle-cards",
        "battle-card-items",
    ):
        template = csv_client.get(f"{BASE}/csv/{entity}/template")
        export = csv_client.get(f"{BASE}/csv/{entity}/export")
        assert template.status_code == export.status_code == 200
        assert "attachment" in template.headers["content-disposition"]
        assert len(template.text.splitlines()) == 2
        assert len(export.text.splitlines()) == 1

    missing_reference = csv_client.get(f"{BASE}/csv/competitor-products/template").text
    result = csv_client.post(
        f"{BASE}/csv/competitor-products/dry-run", json={"csv_text": missing_reference}
    ).json()
    assert not result["valid"]
    assert any(error["code"] == "missing_reference" for error in result["errors"])


def test_competitor_product_csv_resolves_name_and_rejects_unknown_or_duplicate_asin(
    csv_client: TestClient,
) -> None:
    competitor = csv_client.post(f"{BASE}/competitors", json={"name": "CSV Brand"})
    assert competitor.status_code == 201
    template = csv_client.get(f"{BASE}/csv/competitor-products/template").text
    rows = list(csv.reader(io.StringIO(template)))
    columns, sample = rows[0], rows[1]
    sample[columns.index("competitor_name")] = "CSV Brand"
    sample[columns.index("marketplace_product_id")] = "B000000099"
    valid = make_csv(columns, [sample])
    dry_run = csv_client.post(
        f"{BASE}/csv/competitor-products/dry-run", json={"csv_text": valid}
    ).json()
    assert dry_run["valid"] is True
    imported = csv_client.post(f"{BASE}/csv/competitor-products/import", json={"csv_text": valid})
    assert imported.status_code == 200
    assert csv_client.get(f"{BASE}/competitor-products").json()["total"] == 1
    exported = csv_client.get(f"{BASE}/csv/competitor-products/export").text
    assert "competitor_name" in exported.splitlines()[0]
    assert "CSV Brand" in exported

    unknown = sample.copy()
    unknown[columns.index("competitor_name")] = "Unknown Brand"
    unknown[columns.index("marketplace_product_id")] = "B000000098"
    unknown_result = csv_client.post(
        f"{BASE}/csv/competitor-products/dry-run",
        json={"csv_text": make_csv(columns, [unknown])},
    ).json()
    assert unknown_result["valid"] is False
    assert unknown_result["errors"][0]["field"] == "competitor_name"
    assert csv_client.get(f"{BASE}/competitor-products").json()["total"] == 1

    duplicate_one = sample.copy()
    duplicate_two = sample.copy()
    duplicate_one[columns.index("marketplace_product_id")] = "B000000097"
    duplicate_two[columns.index("marketplace_product_id")] = "B000000097"
    duplicate_result = csv_client.post(
        f"{BASE}/csv/competitor-products/dry-run",
        json={"csv_text": make_csv(columns, [duplicate_one, duplicate_two])},
    ).json()
    assert duplicate_result["valid"] is False
    assert any(error["code"] == "duplicate_csv_row" for error in duplicate_result["errors"])


def test_import_rolls_back_when_commit_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = sqlite_engine()
    content = competitor_csv(["Rollback Competitor", "", "", "", "Baby Care", "mid", "3", "", ""])
    with Session(engine) as session:
        service = UniverseCsvService(session)

        def fail_commit() -> None:
            raise RuntimeError("simulated commit failure")

        monkeypatch.setattr(session, "commit", fail_commit)
        with pytest.raises(RuntimeError, match="simulated commit failure"):
            service.import_rows("competitors", content)
        assert session.scalar(select(func.count()).select_from(Competitor)) == 0
    engine.dispose()
