from datetime import UTC, date, datetime
from types import SimpleNamespace

from novel_signal.modules.market_share.router import page
from novel_signal.modules.market_share.schemas import ModelFitRead


def test_page_serializes_orm_shaped_rows_through_read_schema() -> None:
    row = SimpleNamespace(
        id="fit-1",
        platform="amazon",
        marketplace="amazon_in",
        category_node="personal-care",
        pack_size="3 packs",
        model_version="demo-v1",
        trained_from=date(2026, 7, 1),
        trained_to=date(2026, 8, 1),
        sample_count=120,
        metrics={"mape": 12.6},
        input_evidence={"sources": ["amazon_bsr", "own_sales"]},
        status="active",
        created_at=datetime.now(UTC),
    )

    result = page([row], 50, ModelFitRead)

    payload = result.model_dump()
    assert payload["items"][0]["id"] == "fit-1"
    assert payload["items"][0]["sample_count"] == 120
