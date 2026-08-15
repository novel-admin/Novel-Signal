from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from novel_signal.db import Base
from novel_signal.modules.universe.models import (
    CompetitorProduct,
    Marketplace,
    Product,
    TimestampedArchiveMixin,
    TrackingTier,
    enum_column,
)


class KeywordSourceType(StrEnum):
    BRAND_ANALYTICS = "brand_analytics"
    AMAZON_ADS = "amazon_ads"
    AUTOCOMPLETE = "autocomplete"
    REVERSE_ASIN = "reverse_asin"
    GOOGLE_KEYWORD_PLANNER = "google_keyword_planner"
    SEARCH_CONSOLE = "search_console"
    REVIEW_MINING = "review_mining"
    REGIONAL_VARIANT = "regional_variant"
    MANUAL = "manual"


class KeywordTrackingStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"


class IntentCluster(StrEnum):
    GENERIC_CATEGORY = "generic_category"
    ATTRIBUTE_LONG_TAIL = "attribute_long_tail"
    PROBLEM_BENEFIT = "problem_benefit"
    OWN_BRAND = "own_brand"
    COMPETITOR_BRAND = "competitor_brand"
    ADJACENT = "adjacent"
    UNCLASSIFIED = "unclassified"


class Keyword(TimestampedArchiveMixin, Base):
    __tablename__ = "keywords"
    __table_args__ = (
        CheckConstraint("length(trim(keyword_text)) > 0", name="keyword_text_not_blank"),
        CheckConstraint("length(trim(normalized_text)) > 0", name="normalized_text_not_blank"),
        CheckConstraint(
            "volume_estimate IS NULL OR volume_estimate >= 0", name="volume_estimate_nonnegative"
        ),
        CheckConstraint(
            "seasonality_index IS NULL OR seasonality_index >= 0",
            name="seasonality_index_nonnegative",
        ),
        Index("ix_keywords_archived_at", "archived_at"),
        Index("ix_keywords_filters", "marketplace", "tier", "tracking_status", "intent_cluster"),
        Index(
            "uq_keywords_active_identity",
            "marketplace",
            "normalized_text",
            unique=True,
            postgresql_where=text("archived_at IS NULL"),
            sqlite_where=text("archived_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    keyword_text: Mapped[str] = mapped_column(String(500), nullable=False)
    normalized_text: Mapped[str] = mapped_column(String(500), nullable=False)
    marketplace: Mapped[Marketplace] = mapped_column(
        enum_column(Marketplace, "marketplace"), nullable=False
    )
    category: Mapped[str | None] = mapped_column(String(255))
    tier: Mapped[TrackingTier] = mapped_column(
        enum_column(TrackingTier, "tracking_tier"), nullable=False
    )
    tracking_status: Mapped[KeywordTrackingStatus] = mapped_column(
        enum_column(KeywordTrackingStatus, "keyword_tracking_status"),
        default=KeywordTrackingStatus.ACTIVE,
        server_default=KeywordTrackingStatus.ACTIVE.value,
        nullable=False,
    )
    intent_cluster: Mapped[IntentCluster] = mapped_column(
        enum_column(IntentCluster, "keyword_intent_cluster"),
        default=IntentCluster.UNCLASSIFIED,
        server_default=IntentCluster.UNCLASSIFIED.value,
        nullable=False,
    )
    volume_estimate: Mapped[int | None] = mapped_column(Integer)
    trend_metadata: Mapped[dict[str, object] | None] = mapped_column(JSON)
    seasonality_index: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)

    sources: Mapped[list[KeywordSource]] = relationship(
        back_populates="keyword", cascade="all, delete-orphan"
    )
    tracking_targets: Mapped[list[TrackingTarget]] = relationship(
        back_populates="keyword", passive_deletes=True
    )


class KeywordSource(Base):
    __tablename__ = "keyword_sources"
    __table_args__ = (
        UniqueConstraint(
            "keyword_id",
            "source_type",
            "source_reference",
            name="uq_keyword_sources_identity",
        ),
        Index("ix_keyword_sources_keyword_id", "keyword_id"),
        Index("ix_keyword_sources_source_type", "source_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    keyword_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("keywords.id", ondelete="CASCADE"), nullable=False
    )
    source_type: Mapped[KeywordSourceType] = mapped_column(
        enum_column(KeywordSourceType, "keyword_source_type"), nullable=False
    )
    source_reference: Mapped[str] = mapped_column(
        String(500), default="", server_default="", nullable=False
    )
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    source_metadata: Mapped[dict[str, object] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    keyword: Mapped[Keyword] = relationship(back_populates="sources")


class TrackingTarget(TimestampedArchiveMixin, Base):
    __tablename__ = "tracking_targets"
    __table_args__ = (
        CheckConstraint(
            "(product_id IS NOT NULL) <> (competitor_product_id IS NOT NULL)",
            name="exactly_one_target",
        ),
        CheckConstraint("cadence_minutes > 0", name="cadence_positive"),
        Index("ix_tracking_targets_keyword_id", "keyword_id"),
        Index("ix_tracking_targets_product_id", "product_id"),
        Index("ix_tracking_targets_competitor_product_id", "competitor_product_id"),
        Index("ix_tracking_targets_archived_at", "archived_at"),
        Index(
            "uq_tracking_targets_active_product",
            "keyword_id",
            "product_id",
            unique=True,
            postgresql_where=text("archived_at IS NULL AND product_id IS NOT NULL"),
            sqlite_where=text("archived_at IS NULL AND product_id IS NOT NULL"),
        ),
        Index(
            "uq_tracking_targets_active_competitor_product",
            "keyword_id",
            "competitor_product_id",
            unique=True,
            postgresql_where=text("archived_at IS NULL AND competitor_product_id IS NOT NULL"),
            sqlite_where=text("archived_at IS NULL AND competitor_product_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    keyword_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("keywords.id", ondelete="RESTRICT"), nullable=False
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT")
    )
    competitor_product_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("competitor_products.id", ondelete="RESTRICT")
    )
    cadence_minutes: Mapped[int] = mapped_column(
        Integer, default=240, server_default="240", nullable=False
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )

    keyword: Mapped[Keyword] = relationship(back_populates="tracking_targets")
    product: Mapped[Product | None] = relationship(back_populates="tracking_targets")
    competitor_product: Mapped[CompetitorProduct | None] = relationship(
        back_populates="tracking_targets"
    )
