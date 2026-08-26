from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from novel_signal.modules.price_monitoring.models import (
    AvailabilityStatus,
    CouponType,
    PriceEventType,
)
from novel_signal.modules.universe.models import Marketplace

Money = Decimal | None


class FreshnessStatus(StrEnum):
    FRESH = "fresh"
    STALE = "stale"
    UNKNOWN = "unknown"


class Read(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class SellerOfferIn(BaseModel):
    seller_name: str = Field(min_length=1, max_length=500)
    seller_id: str | None = None
    offer_price: Money = Field(default=None, ge=0)
    list_price: Money = Field(default=None, ge=0)
    shipping_amount: Money = Field(default=None, ge=0)
    coupon_text: str | None = None
    coupon_value: Money = Field(default=None, ge=0)
    effective_price: Money = Field(default=None, ge=0)
    availability_status: AvailabilityStatus = AvailabilityStatus.UNKNOWN
    fulfillment_type: str | None = None
    is_featured_offer: bool | None = None
    prime_eligible: bool | None = None
    offer_metadata: dict[str, object] | None = None

    @field_validator("seller_name")
    @classmethod
    def clean_seller(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("seller_name must not be blank")
        return value.strip()


class SellerOfferRead(Read):
    id: uuid.UUID
    observation_id: uuid.UUID
    seller_name: str
    seller_id: str | None
    offer_price: Money
    list_price: Money
    shipping_amount: Money
    coupon_text: str | None
    coupon_value: Money
    effective_price: Money
    availability_status: AvailabilityStatus
    fulfillment_type: str | None
    is_featured_offer: bool | None
    prime_eligible: bool | None
    offer_metadata: dict[str, object] | None


class PriceObservationIn(BaseModel):
    marketplace: Marketplace = Marketplace.AMAZON_IN
    marketplace_product_id: str = Field(min_length=1, max_length=255)
    observed_at: datetime
    geo_code: str | None = None
    device_profile: str | None = None
    currency: str = Field(default="INR", min_length=3, max_length=3)
    availability_status: AvailabilityStatus = AvailabilityStatus.UNKNOWN
    primary_price: Money = Field(default=None, ge=0)
    mrp: Money = Field(default=None, ge=0)
    discount_percent: Money = Field(default=None, ge=0, le=100)
    coupon_text: str | None = None
    coupon_value: Money = Field(default=None, ge=0)
    coupon_type: CouponType | None = None
    shipping_amount: Money = Field(default=None, ge=0)
    effective_price: Money = Field(default=None, ge=0)
    primary_seller_name: str | None = None
    primary_seller_id: str | None = None
    is_featured_offer: bool | None = None
    seller_count: int | None = Field(default=None, ge=0)
    offers: list[SellerOfferIn] = Field(default_factory=list)
    source_job_id: uuid.UUID | None = None
    parser_version: str | None = None
    source_url: str | None = None
    ingestion_key: str | None = Field(default=None, min_length=1)
    provider: str | None = None
    source_metadata: dict[str, object] | None = None

    @field_validator("marketplace_product_id", "currency")
    @classmethod
    def clean_required(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be blank")
        return value.strip().upper() if len(value.strip()) == 3 else value.strip()

    @model_validator(mode="after")
    def unavailable_has_no_invented_zero(self) -> Self:
        if (
            self.availability_status
            in {AvailabilityStatus.UNAVAILABLE, AvailabilityStatus.OUT_OF_STOCK}
            and self.primary_price is not None
        ):
            raise ValueError("unavailable observations cannot contain a primary price")
        identities = [(offer.seller_id or offer.seller_name).casefold() for offer in self.offers]
        if len(identities) != len(set(identities)):
            raise ValueError("duplicate seller offer identity")
        if (
            self.seller_count is not None
            and self.offers
            and self.seller_count != len(set(identities))
        ):
            raise ValueError("seller_count must match unique offers")
        return self


class PriceObservationRead(Read):
    id: uuid.UUID
    marketplace: Marketplace
    marketplace_product_id: str
    product_id: uuid.UUID | None
    competitor_product_id: uuid.UUID | None
    observed_at: datetime
    geo_code: str | None
    device_profile: str | None
    currency: str
    availability_status: AvailabilityStatus
    primary_price: Money
    list_price: Money
    discount_percent: Money
    coupon_text: str | None
    coupon_value: Money
    coupon_type: CouponType | None
    shipping_amount: Money
    effective_price: Money
    primary_seller_name: str | None
    primary_seller_id: str | None
    is_featured_offer: bool | None
    seller_count: int | None
    source_job_id: uuid.UUID | None
    parser_version: str | None
    source_url: str | None
    ingestion_key: str | None
    provider: str | None
    source_metadata: dict[str, object] | None
    offers: list[SellerOfferRead]
    created_at: datetime
    updated_at: datetime


class PriceObservationList(BaseModel):
    items: list[PriceObservationRead]
    total: int
    limit: int
    offset: int


class Freshness(BaseModel):
    observed_at: datetime
    age_minutes: int
    freshness_status: FreshnessStatus


class LatestPrice(BaseModel):
    observation: PriceObservationRead
    freshness: Freshness


class PriceHistoryRow(BaseModel):
    id: uuid.UUID
    observed_at: datetime
    primary_price: Money
    mrp: Money
    effective_price: Money
    discount_percent: Money
    coupon_text: str | None
    shipping_amount: Money
    availability_status: AvailabilityStatus
    seller_count: int | None
    primary_seller_name: str | None
    geo_code: str | None
    currency: str


class PriceHistoryList(BaseModel):
    items: list[PriceHistoryRow]
    total: int
    limit: int
    offset: int


class PriceChangeEventRead(Read):
    id: uuid.UUID
    observation_id: uuid.UUID
    previous_observation_id: uuid.UUID | None
    marketplace_product_id: str
    product_id: uuid.UUID | None
    competitor_product_id: uuid.UUID | None
    event_type: PriceEventType
    previous_price: Money
    new_price: Money
    absolute_change: Money
    percent_change: Money
    geo_code: str | None
    currency: str
    observed_at: datetime


class PriceChangeEventList(BaseModel):
    items: list[PriceChangeEventRead]
    total: int
    limit: int
    offset: int


class PriceMetrics(BaseModel):
    latest_price: Money
    minimum_price: Money
    maximum_price: Money
    average_price: Money
    observation_count: int
    latest_mrp: Money
    latest_discount: Money
    latest_effective_price: Money
    last_movement_amount: Money
    last_movement_percent: Money


class PriceSide(BaseModel):
    primary_price: Money
    effective_price: Money
    mrp: Money
    discount_percent: Money
    seller_count: int | None
    availability_status: AvailabilityStatus
    freshness: Freshness


class PriceComparison(BaseModel):
    owned: PriceSide
    competitor: PriceSide
    deltas: dict[str, Decimal | int | None]
    signals: list[str]


class PricePerUnitSide(BaseModel):
    observation_id: uuid.UUID
    price: Money
    pack_quantity: int | None
    pack_unit: str | None
    price_per_unit: Money


class PricePerUnitComparison(BaseModel):
    owned: PricePerUnitSide
    competitor: PricePerUnitSide
    comparable: bool
    unit: str | None
    difference: Money
