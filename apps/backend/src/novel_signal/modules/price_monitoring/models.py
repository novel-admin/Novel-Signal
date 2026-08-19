from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from novel_signal.db import Base
from novel_signal.modules.universe.models import Marketplace, enum_column


class AvailabilityStatus(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"
    LIMITED = "limited"
    OUT_OF_STOCK = "out_of_stock"


class CouponType(StrEnum):
    ABSOLUTE = "absolute"
    PERCENTAGE = "percentage"
    UNCERTAIN = "uncertain"


class PriceEventType(StrEnum):
    PRICE_INCREASE = "price_increase"
    PRICE_DECREASE = "price_decrease"
    BECAME_AVAILABLE = "became_available"
    BECAME_UNAVAILABLE = "became_unavailable"


class PriceObservation(Base):
    __tablename__ = "price_observations"
    __table_args__ = (
        CheckConstraint(
            "length(trim(marketplace_product_id)) > 0", name="marketplace_product_id_not_blank"
        ),
        CheckConstraint("length(trim(currency)) > 0", name="currency_not_blank"),
        CheckConstraint(
            "NOT (product_id IS NOT NULL AND competitor_product_id IS NOT NULL)",
            name="single_product_mapping",
        ),
        CheckConstraint(
            "primary_price IS NULL OR primary_price >= 0", name="primary_price_nonnegative"
        ),
        CheckConstraint("list_price IS NULL OR list_price >= 0", name="list_price_nonnegative"),
        CheckConstraint(
            "shipping_amount IS NULL OR shipping_amount >= 0", name="shipping_nonnegative"
        ),
        CheckConstraint(
            "coupon_value IS NULL OR coupon_value >= 0", name="coupon_value_nonnegative"
        ),
        CheckConstraint(
            "effective_price IS NULL OR effective_price >= 0", name="effective_price_nonnegative"
        ),
        CheckConstraint(
            "discount_percent IS NULL OR discount_percent BETWEEN 0 AND 100",
            name="discount_percent_range",
        ),
        CheckConstraint(
            "seller_count IS NULL OR seller_count >= 0", name="seller_count_nonnegative"
        ),
        UniqueConstraint("ingestion_key", name="uq_price_observations_ingestion_key"),
        Index(
            "ix_price_observations_identity_observed",
            "marketplace",
            "marketplace_product_id",
            "geo_code",
            "observed_at",
        ),
        Index("ix_price_observations_product_observed", "product_id", "geo_code", "observed_at"),
        Index(
            "ix_price_observations_competitor_observed",
            "competitor_product_id",
            "geo_code",
            "observed_at",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    marketplace: Mapped[Marketplace] = mapped_column(
        enum_column(Marketplace, "marketplace"), nullable=False
    )
    marketplace_product_id: Mapped[str] = mapped_column(String(255), nullable=False)
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT")
    )
    competitor_product_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("competitor_products.id", ondelete="RESTRICT")
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    geo_code: Mapped[str | None] = mapped_column(String(50))
    device_profile: Mapped[str | None] = mapped_column(String(50))
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    availability_status: Mapped[AvailabilityStatus] = mapped_column(
        enum_column(AvailabilityStatus, "price_availability_status"), nullable=False
    )
    primary_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    list_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    discount_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    coupon_text: Mapped[str | None] = mapped_column(Text)
    coupon_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    coupon_type: Mapped[CouponType | None] = mapped_column(
        enum_column(CouponType, "price_coupon_type")
    )
    shipping_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    effective_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    primary_seller_name: Mapped[str | None] = mapped_column(String(500))
    primary_seller_id: Mapped[str | None] = mapped_column(String(255))
    is_featured_offer: Mapped[bool | None] = mapped_column(Boolean)
    seller_count: Mapped[int | None] = mapped_column(Integer)
    source_job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("collection_jobs.id", ondelete="SET NULL")
    )
    parser_version: Mapped[str | None] = mapped_column(String(100))
    source_url: Mapped[str | None] = mapped_column(String(2048))
    ingestion_key: Mapped[str | None] = mapped_column(String(255))
    provider: Mapped[str | None] = mapped_column(String(100))
    source_metadata: Mapped[dict[str, object] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    offers: Mapped[list[SellerOffer]] = relationship(
        back_populates="observation", cascade="all, delete-orphan"
    )
    events: Mapped[list[PriceChangeEvent]] = relationship(
        back_populates="observation",
        cascade="all, delete-orphan",
        foreign_keys="PriceChangeEvent.observation_id",
    )


class SellerOffer(Base):
    __tablename__ = "seller_offers"
    __table_args__ = (
        CheckConstraint("length(trim(seller_name)) > 0", name="seller_name_not_blank"),
        CheckConstraint("offer_price IS NULL OR offer_price >= 0", name="offer_price_nonnegative"),
        CheckConstraint("list_price IS NULL OR list_price >= 0", name="list_price_nonnegative"),
        CheckConstraint(
            "shipping_amount IS NULL OR shipping_amount >= 0", name="shipping_nonnegative"
        ),
        CheckConstraint(
            "coupon_value IS NULL OR coupon_value >= 0", name="coupon_value_nonnegative"
        ),
        CheckConstraint(
            "effective_price IS NULL OR effective_price >= 0", name="effective_price_nonnegative"
        ),
        UniqueConstraint(
            "observation_id",
            "seller_name",
            "seller_id",
            name="uq_seller_offers_observation_identity",
        ),
        Index("ix_seller_offers_observation", "observation_id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    observation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("price_observations.id", ondelete="CASCADE"), nullable=False
    )
    seller_name: Mapped[str] = mapped_column(String(500), nullable=False)
    seller_id: Mapped[str | None] = mapped_column(String(255))
    offer_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    list_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    shipping_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    coupon_text: Mapped[str | None] = mapped_column(Text)
    coupon_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    effective_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    availability_status: Mapped[AvailabilityStatus] = mapped_column(
        enum_column(AvailabilityStatus, "price_availability_status"), nullable=False
    )
    fulfillment_type: Mapped[str | None] = mapped_column(String(100))
    is_featured_offer: Mapped[bool | None] = mapped_column(Boolean)
    prime_eligible: Mapped[bool | None] = mapped_column(Boolean)
    offer_metadata: Mapped[dict[str, object] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    observation: Mapped[PriceObservation] = relationship(back_populates="offers")


class PriceChangeEvent(Base):
    __tablename__ = "price_change_events"
    __table_args__ = (
        UniqueConstraint("observation_id", "event_type", name="uq_price_events_observation_type"),
        Index(
            "ix_price_events_identity_observed", "marketplace_product_id", "geo_code", "observed_at"
        ),
        Index("ix_price_events_product_observed", "product_id", "observed_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    observation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("price_observations.id", ondelete="CASCADE"), nullable=False
    )
    previous_observation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("price_observations.id", ondelete="SET NULL")
    )
    marketplace: Mapped[Marketplace] = mapped_column(
        enum_column(Marketplace, "marketplace"), nullable=False
    )
    marketplace_product_id: Mapped[str] = mapped_column(String(255), nullable=False)
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT")
    )
    competitor_product_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("competitor_products.id", ondelete="RESTRICT")
    )
    event_type: Mapped[PriceEventType] = mapped_column(
        enum_column(PriceEventType, "price_event_type"), nullable=False
    )
    previous_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    new_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    absolute_change: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    percent_change: Mapped[Decimal | None] = mapped_column(Numeric(9, 2))
    geo_code: Mapped[str | None] = mapped_column(String(50))
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    observation: Mapped[PriceObservation] = relationship(
        back_populates="events", foreign_keys=[observation_id]
    )
