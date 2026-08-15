import pytest
from novel_signal.modules.market_share.schemas import MarketShareCreate, UnitsEstimateCreate
from pydantic import ValidationError


def estimate(**overrides: object) -> UnitsEstimateCreate:
    values: dict[str, object] = {
        "model_fit_id": "fit-1",
        "platform": "amazon",
        "marketplace": "amazon.in",
        "category_node": "cat-1",
        "entity_type": "competitor_product",
        "entity_id": "sku-1",
        "observed_on": "2026-08-15",
        "units_low": 10,
        "units_point": 15,
        "units_high": 20,
        "revenue_low": 1000,
        "revenue_point": 1500,
        "revenue_high": 2000,
        "confidence": "medium",
        "input_coverage": 0.8,
        "method": "bsr_power_law:v1",
        "model_version": "bsr-v1",
    }
    values.update(overrides)
    return UnitsEstimateCreate.model_validate(values)


def test_estimate_requires_range_containing_point() -> None:
    with pytest.raises(ValidationError, match="unit bounds"):
        estimate(units_low=20, units_point=15)


def test_divergent_cross_check_requires_warning() -> None:
    with pytest.raises(ValidationError, match="divergent cross-check"):
        estimate(cross_check_units=30)


def test_share_bounds_are_explicit() -> None:
    share = MarketShareCreate(
        platform="amazon",
        marketplace="amazon.in",
        category_node="cat-1",
        entity_type="brand",
        entity_id="brand-1",
        observed_on="2026-08-15",
        units_low=10,
        units_point=15,
        units_high=20,
        share_low=0.1,
        share_point=0.15,
        share_high=0.2,
        confidence="low",
        input_coverage=0.4,
        model_version="bsr-v1",
    )
    assert share.share_low <= share.share_point <= share.share_high
