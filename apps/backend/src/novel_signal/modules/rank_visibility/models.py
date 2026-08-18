from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from novel_signal.db import Base
from novel_signal.modules.universe.models import Marketplace, enum_column


class DeviceProfile(StrEnum):
    DESKTOP = "desktop"
    MOBILE = "mobile"


class PlacementType(StrEnum):
    ORGANIC = "organic"
    SPONSORED_PRODUCT = "sponsored_product"
    SPONSORED_BRAND = "sponsored_brand"
    SPONSORED_BRAND_VIDEO = "sponsored_brand_video"
    SPONSORED_DISPLAY = "sponsored_display"
    EDITORIAL_OR_DEAL = "editorial_or_deal"


class BadgeType(StrEnum):
    BEST_SELLER = "best_seller"
    AMAZONS_CHOICE = "amazons_choice"
    DEAL = "deal"
    LIMITED_TIME_DEAL = "limited_time_deal"
    NEW_ARRIVAL = "new_arrival"
    SPONSORED = "sponsored"


class BadgeEventType(StrEnum):
    ACQUIRED = "acquired"
    LOST = "lost"


class SerpCapture(Base):
    __tablename__ = "serp_captures"
    __table_args__ = (
        CheckConstraint("length(trim(geo_code)) > 0", name="geo_code_not_blank"),
        CheckConstraint("page_count >= 0", name="page_count_nonnegative"),
        CheckConstraint("result_count >= 0", name="result_count_nonnegative"),
        Index("ix_serp_captures_keyword_captured", "keyword_id", "captured_at"),
        Index("ix_serp_captures_marketplace_captured", "marketplace", "captured_at"),
        Index(
            "ix_serp_captures_context_captured",
            "keyword_id",
            "marketplace",
            "geo_code",
            "device_profile",
            "captured_at",
        ),
        UniqueConstraint("ingestion_key", name="uq_serp_captures_ingestion_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    keyword_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("keywords.id", ondelete="RESTRICT"), nullable=False
    )
    marketplace: Mapped[Marketplace] = mapped_column(
        enum_column(Marketplace, "marketplace"), nullable=False
    )
    geo_code: Mapped[str] = mapped_column(String(50), nullable=False)
    device_profile: Mapped[DeviceProfile] = mapped_column(
        enum_column(DeviceProfile, "device_profile"), nullable=False
    )
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False)
    result_count: Mapped[int] = mapped_column(Integer, nullable=False)
    source_job_id: Mapped[str | None] = mapped_column(String(255))
    parser_version: Mapped[str | None] = mapped_column(String(100))
    ingestion_key: Mapped[str | None] = mapped_column(String(255))
    capture_metadata: Mapped[dict[str, object] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    results: Mapped[list[SerpResult]] = relationship(
        back_populates="capture",
        cascade="all, delete-orphan",
        order_by="SerpResult.absolute_position",
    )


class SerpResult(Base):
    __tablename__ = "serp_results"
    __table_args__ = (
        CheckConstraint("absolute_position > 0", name="absolute_position_positive"),
        CheckConstraint("within_type_position > 0", name="within_type_position_positive"),
        CheckConstraint("page_number > 0", name="page_number_positive"),
        CheckConstraint(
            "length(trim(marketplace_product_id)) > 0", name="marketplace_product_id_not_blank"
        ),
        CheckConstraint(
            "displayed_price IS NULL OR displayed_price >= 0", name="price_nonnegative"
        ),
        CheckConstraint("mrp IS NULL OR mrp >= 0", name="mrp_nonnegative"),
        CheckConstraint(
            "discount_percent IS NULL OR discount_percent BETWEEN 0 AND 100",
            name="discount_percent_range",
        ),
        CheckConstraint("rating IS NULL OR rating BETWEEN 0 AND 5", name="rating_range"),
        CheckConstraint(
            "review_count IS NULL OR review_count >= 0", name="review_count_nonnegative"
        ),
        CheckConstraint(
            "NOT (product_id IS NOT NULL AND competitor_product_id IS NOT NULL)",
            name="at_most_one_product_mapping",
        ),
        UniqueConstraint(
            "capture_id", "absolute_position", name="uq_serp_results_capture_position"
        ),
        Index("ix_serp_results_capture_id", "capture_id"),
        Index("ix_serp_results_marketplace_product_id", "marketplace_product_id"),
        Index("ix_serp_results_product_id", "product_id"),
        Index("ix_serp_results_competitor_product_id", "competitor_product_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    capture_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("serp_captures.id", ondelete="CASCADE"), nullable=False
    )
    absolute_position: Mapped[int] = mapped_column(Integer, nullable=False)
    within_type_position: Mapped[int] = mapped_column(Integer, nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    marketplace_product_id: Mapped[str] = mapped_column(String(255), nullable=False)
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT")
    )
    competitor_product_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("competitor_products.id", ondelete="RESTRICT")
    )
    brand: Mapped[str | None] = mapped_column(String(255))
    placement_type: Mapped[PlacementType] = mapped_column(
        enum_column(PlacementType, "serp_placement_type"), nullable=False
    )
    badges: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    amazons_choice_term: Mapped[str | None] = mapped_column(String(500))
    displayed_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    mrp: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    discount_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    coupon: Mapped[str | None] = mapped_column(String(500))
    delivery_promise: Mapped[str | None] = mapped_column(String(500))
    rating: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    review_count: Mapped[int | None] = mapped_column(Integer)
    thumbnail_hash: Mapped[str | None] = mapped_column(String(255))
    result_metadata: Mapped[dict[str, object] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    capture: Mapped[SerpCapture] = relationship(back_populates="results")


class BadgeEvent(Base):
    __tablename__ = "badge_events"
    __table_args__ = (
        UniqueConstraint(
            "capture_id",
            "result_id",
            "badge_type",
            "event_type",
            name="uq_badge_events_observation",
        ),
        Index("ix_badge_events_keyword_observed", "keyword_id", "observed_at"),
        Index("ix_badge_events_marketplace_product_id", "marketplace_product_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    keyword_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("keywords.id", ondelete="RESTRICT"))
    capture_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("serp_captures.id", ondelete="CASCADE")
    )
    result_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("serp_results.id", ondelete="CASCADE"))
    marketplace_product_id: Mapped[str] = mapped_column(String(255), nullable=False)
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT")
    )
    competitor_product_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("competitor_products.id", ondelete="RESTRICT")
    )
    brand: Mapped[str | None] = mapped_column(String(255))
    badge_type: Mapped[BadgeType] = mapped_column(enum_column(BadgeType, "badge_type"))
    event_type: Mapped[BadgeEventType] = mapped_column(
        enum_column(BadgeEventType, "badge_event_type")
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class NewEntrantEvent(Base):
    __tablename__ = "new_entrant_events"
    __table_args__ = (
        UniqueConstraint(
            "keyword_id",
            "marketplace",
            "marketplace_product_id",
            "geo_code",
            "device_profile",
            name="uq_new_entrant_events_context_identity",
        ),
        Index("ix_new_entrant_events_keyword_first_seen", "keyword_id", "first_seen_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    keyword_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("keywords.id", ondelete="RESTRICT"))
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
    first_seen_capture_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("serp_captures.id", ondelete="CASCADE")
    )
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    brand: Mapped[str | None] = mapped_column(String(255))
    geo_code: Mapped[str] = mapped_column(String(50), nullable=False)
    device_profile: Mapped[DeviceProfile] = mapped_column(
        enum_column(DeviceProfile, "device_profile"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
