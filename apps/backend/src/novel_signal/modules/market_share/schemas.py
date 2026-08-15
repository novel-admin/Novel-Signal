from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Confidence = Literal["high", "medium", "low"]


class ModelFitCreate(BaseModel):
    platform: str = Field(min_length=1, max_length=40)
    marketplace: str = Field(min_length=1, max_length=80)
    category_node: str = Field(min_length=1, max_length=160)
    pack_size: str | None = None
    model_version: str = Field(min_length=1, max_length=80)
    trained_from: date
    trained_to: date
    sample_count: int = Field(ge=1)
    metrics: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def valid_dates(self) -> "ModelFitCreate":
        if self.trained_to < self.trained_from:
            raise ValueError("trained_to must not be before trained_from")
        return self


class ModelFitRead(ModelFitCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str
    status: str
    created_at: datetime


class UnitsEstimateCreate(BaseModel):
    model_fit_id: str
    platform: str
    marketplace: str
    category_node: str
    entity_type: str
    entity_id: str
    brand_id: str | None = None
    observed_on: date
    bsr: int | None = Field(default=None, ge=1)
    price: float | None = Field(default=None, ge=0)
    units_low: float = Field(ge=0)
    units_point: float = Field(ge=0)
    units_high: float = Field(ge=0)
    revenue_low: float = Field(ge=0)
    revenue_point: float = Field(ge=0)
    revenue_high: float = Field(ge=0)
    confidence: Confidence
    input_coverage: float = Field(ge=0, le=1)
    method: str
    cross_check_units: float | None = Field(default=None, ge=0)
    divergence_warning: str | None = None
    model_version: str

    @model_validator(mode="after")
    def valid_ranges(self) -> "UnitsEstimateCreate":
        if not self.units_low <= self.units_point <= self.units_high:
            raise ValueError("unit bounds must contain units_point")
        if not self.revenue_low <= self.revenue_point <= self.revenue_high:
            raise ValueError("revenue bounds must contain revenue_point")
        if self.cross_check_units is not None and self.units_point > 0:
            ratio = abs(self.cross_check_units - self.units_point) / self.units_point
            if ratio >= 0.5 and not self.divergence_warning:
                raise ValueError("divergent cross-check requires divergence_warning")
        return self


class UnitsEstimateRead(UnitsEstimateCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str
    created_at: datetime


class MarketShareCreate(BaseModel):
    platform: str
    marketplace: str
    category_node: str
    entity_type: str
    entity_id: str
    brand_id: str | None = None
    observed_on: date
    segment_key: str = "all"
    units_low: float = Field(ge=0)
    units_point: float = Field(ge=0)
    units_high: float = Field(ge=0)
    share_low: float = Field(ge=0, le=1)
    share_point: float = Field(ge=0, le=1)
    share_high: float = Field(ge=0, le=1)
    confidence: Confidence
    input_coverage: float = Field(ge=0, le=1)
    model_version: str
    divergence_warning: str | None = None

    @model_validator(mode="after")
    def valid_ranges(self) -> "MarketShareCreate":
        if not self.units_low <= self.units_point <= self.units_high:
            raise ValueError("unit bounds must contain units_point")
        if not self.share_low <= self.share_point <= self.share_high:
            raise ValueError("share bounds must contain share_point")
        return self


class MarketShareRead(MarketShareCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str


class BacktestCreate(BaseModel):
    model_fit_id: str
    model_version: str
    period_start: date
    period_end: date
    sample_count: int = Field(ge=1)
    actual_units: float = Field(ge=0)
    predicted_units: float = Field(ge=0)
    mae: float = Field(ge=0)
    mape: float | None = Field(default=None, ge=0)
    metrics: dict[str, Any] = Field(default_factory=dict)


class BacktestRead(BacktestCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str
    created_at: datetime


class Page(BaseModel):
    items: list[Any]
    next_cursor: str | None = None
