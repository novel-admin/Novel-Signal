from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from novel_signal.modules.rank_visibility.models import (
    BadgeEventType,
    BadgeType,
    DeviceProfile,
    PlacementType,
)
from novel_signal.modules.universe.models import Marketplace


class ReadModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class SerpResultIn(BaseModel):
    absolute_position: int = Field(gt=0)
    within_type_position: int | None = Field(default=None, gt=0)
    page_number: int = Field(gt=0)
    marketplace_product_id: str = Field(min_length=1, max_length=255)
    brand: str | None = Field(default=None, max_length=255)
    placement_type: PlacementType
    badges: list[BadgeType] = Field(default_factory=list)
    amazons_choice_term: str | None = Field(default=None, max_length=500)
    displayed_price: Decimal | None = Field(default=None, ge=0)
    mrp: Decimal | None = Field(default=None, ge=0)
    discount_percent: Decimal | None = Field(default=None, ge=0, le=100)
    coupon: str | None = Field(default=None, max_length=500)
    delivery_promise: str | None = Field(default=None, max_length=500)
    rating: Decimal | None = Field(default=None, ge=0, le=5)
    review_count: int | None = Field(default=None, ge=0)
    thumbnail_hash: str | None = Field(default=None, max_length=255)
    result_metadata: dict[str, object] | None = None

    @field_validator("marketplace_product_id")
    @classmethod
    def strip_marketplace_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("marketplace_product_id must not be blank")
        return value.strip()


class CaptureIngest(BaseModel):
    keyword_id: uuid.UUID
    marketplace: Marketplace = Marketplace.AMAZON_IN
    geo_code: str = Field(min_length=1, max_length=50)
    device_profile: DeviceProfile
    captured_at: datetime
    source_job_id: str | None = Field(default=None, max_length=255)
    parser_version: str | None = Field(default=None, max_length=100)
    ingestion_key: str | None = Field(default=None, min_length=1, max_length=255)
    capture_metadata: dict[str, object] | None = None
    results: list[SerpResultIn] = Field(min_length=1)

    @field_validator("geo_code")
    @classmethod
    def strip_geo(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("geo_code must not be blank")
        return value.strip()

    @model_validator(mode="after")
    def positions_are_unique(self) -> Self:
        positions = [row.absolute_position for row in self.results]
        if len(positions) != len(set(positions)):
            raise ValueError("absolute_position must be unique inside a capture")
        return self


class SerpResultRead(ReadModel):
    id: uuid.UUID
    capture_id: uuid.UUID
    absolute_position: int
    within_type_position: int
    page_number: int
    marketplace_product_id: str
    product_id: uuid.UUID | None
    competitor_product_id: uuid.UUID | None
    brand: str | None
    placement_type: PlacementType
    badges: list[str]
    amazons_choice_term: str | None
    displayed_price: Decimal | None
    mrp: Decimal | None
    discount_percent: Decimal | None
    coupon: str | None
    delivery_promise: str | None
    rating: Decimal | None
    review_count: int | None
    thumbnail_hash: str | None
    result_metadata: dict[str, object] | None
    created_at: datetime


class CaptureSummary(ReadModel):
    id: uuid.UUID
    keyword_id: uuid.UUID
    marketplace: Marketplace
    geo_code: str
    device_profile: DeviceProfile
    captured_at: datetime
    page_count: int
    result_count: int
    source_job_id: str | None
    parser_version: str | None
    ingestion_key: str | None
    capture_metadata: dict[str, object] | None
    created_at: datetime
    updated_at: datetime


class CaptureDetail(CaptureSummary):
    results: list[SerpResultRead]


class CaptureList(BaseModel):
    items: list[CaptureSummary]
    total: int
    limit: int
    offset: int


class RankObservation(BaseModel):
    capture_id: uuid.UUID
    captured_at: datetime
    absolute_position: int
    organic_rank: int | None
    placement_type: PlacementType
    page_number: int
    displayed_price: Decimal | None
    rating: Decimal | None
    review_count: int | None


class RankHistory(BaseModel):
    keyword_id: uuid.UUID
    identity: str
    observations: list[RankObservation]


class VisibilityMetrics(BaseModel):
    keyword_id: uuid.UUID
    identity: str
    latest_rank: int | None
    best_rank: int | None
    latest_organic_rank: int | None
    observation_count: int
    rank_volatility: float
    time_in_top_3_percent: float
    time_in_top_10_percent: float


class BrandPresenceRow(BaseModel):
    brand: str
    page_1_slot_count: int
    page_1_share_percent: float
    organic_slots: int
    sponsored_slots: int


class BrandPresence(BaseModel):
    total_page_1_results: int
    brands: list[BrandPresenceRow]


class ReverseAsinKeyword(BaseModel):
    keyword_id: uuid.UUID
    keyword_text: str
    latest_position: int
    latest_organic_position: int | None
    sponsored_present: bool
    first_observed_at: datetime
    latest_observed_at: datetime
    latest_capture_id: uuid.UUID
    latest_result_ids: list[uuid.UUID]
    marketplace: Marketplace
    geo_code: str
    device_profile: DeviceProfile
    source_job_id: str | None
    parser_version: str | None


class ReverseAsinIntelligence(BaseModel):
    identity: str
    keyword_count: int
    context_count: int
    keywords: list[ReverseAsinKeyword]


class ShareOfVoiceMetric(BaseModel):
    matched_slots: int
    eligible_slots: int
    share_percent: float


class AmazonShareOfVoice(BaseModel):
    capture_id: uuid.UUID
    keyword_id: uuid.UUID
    captured_at: datetime
    marketplace: Marketplace
    geo_code: str
    device_profile: DeviceProfile
    identity: str
    organic: ShareOfVoiceMetric
    paid: ShareOfVoiceMetric
    total: ShareOfVoiceMetric
    matched_result_ids: list[uuid.UUID]
    source_job_id: str | None
    parser_version: str | None


class KeywordGapRow(BaseModel):
    keyword_id: uuid.UUID
    capture_id: uuid.UUID
    captured_at: datetime
    geo_code: str
    device_profile: DeviceProfile
    owned_present: bool
    competitor_present: bool
    owned_organic_present: bool
    competitor_organic_present: bool
    owned_paid_present: bool
    competitor_paid_present: bool
    gap_types: list[str]
    competitor_result_ids: list[uuid.UUID]
    source_job_id: str | None
    parser_version: str | None


class KeywordGapAnalysis(BaseModel):
    owned_product_id: uuid.UUID
    competitor_product_id: uuid.UUID
    contexts_checked: int
    gap_count: int
    gaps: list[KeywordGapRow]


class BadgeEventRead(ReadModel):
    id: uuid.UUID
    keyword_id: uuid.UUID
    capture_id: uuid.UUID
    result_id: uuid.UUID
    marketplace_product_id: str
    product_id: uuid.UUID | None
    competitor_product_id: uuid.UUID | None
    brand: str | None
    badge_type: BadgeType
    event_type: BadgeEventType
    observed_at: datetime
    created_at: datetime


class BadgeEventList(BaseModel):
    items: list[BadgeEventRead]
    total: int
    limit: int
    offset: int


class NewEntrantRead(ReadModel):
    id: uuid.UUID
    keyword_id: uuid.UUID
    marketplace: Marketplace
    marketplace_product_id: str
    product_id: uuid.UUID | None
    competitor_product_id: uuid.UUID | None
    first_seen_capture_id: uuid.UUID
    first_seen_at: datetime
    rank: int
    brand: str | None
    geo_code: str
    device_profile: DeviceProfile
    created_at: datetime


class NewEntrantList(BaseModel):
    items: list[NewEntrantRead]
    total: int
    limit: int
    offset: int
