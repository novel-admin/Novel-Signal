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
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from novel_signal.db import Base
from novel_signal.modules.universe.models import Marketplace, enum_column


class ListingChangeType(StrEnum):
    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"


class ListingSnapshot(Base):
    __tablename__ = "listing_snapshots"
    __table_args__ = (
        CheckConstraint(
            "length(trim(marketplace_product_id)) > 0", name="marketplace_product_id_not_blank"
        ),
        CheckConstraint(
            "NOT (product_id IS NOT NULL AND competitor_product_id IS NOT NULL)",
            name="single_product_mapping",
        ),
        CheckConstraint("image_count >= 0", name="image_count_nonnegative"),
        CheckConstraint("video_count >= 0", name="video_count_nonnegative"),
        CheckConstraint(
            "variation_count IS NULL OR variation_count >= 0", name="variation_count_nonnegative"
        ),
        CheckConstraint("completeness_score BETWEEN 0 AND 100", name="completeness_score_range"),
        UniqueConstraint("ingestion_key", name="uq_listing_snapshots_ingestion_key"),
        Index(
            "ix_listing_snapshots_identity_captured",
            "marketplace",
            "marketplace_product_id",
            "captured_at",
        ),
        Index("ix_listing_snapshots_product_captured", "product_id", "captured_at"),
        Index("ix_listing_snapshots_competitor_captured", "competitor_product_id", "captured_at"),
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
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    geo_code: Mapped[str | None] = mapped_column(String(50))
    device_profile: Mapped[str | None] = mapped_column(String(30))
    source_job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("collection_jobs.id", ondelete="SET NULL")
    )
    parser_version: Mapped[str | None] = mapped_column(String(100))
    ingestion_key: Mapped[str | None] = mapped_column(String(255))
    source_url: Mapped[str | None] = mapped_column(String(2048))
    title: Mapped[str | None] = mapped_column(Text)
    brand: Mapped[str | None] = mapped_column(String(255))
    category_path: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    bullets: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    key_features: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    a_plus_present: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    a_plus_sections: Mapped[list[object]] = mapped_column(JSON, default=list, nullable=False)
    image_urls: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    image_hashes: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    image_count: Mapped[int] = mapped_column(Integer, nullable=False)
    video_present: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    video_count: Mapped[int] = mapped_column(Integer, nullable=False)
    variation_count: Mapped[int | None] = mapped_column(Integer)
    variation_metadata: Mapped[dict[str, object] | None] = mapped_column(JSON)
    storefront_text: Mapped[str | None] = mapped_column(Text)
    content_metadata: Mapped[dict[str, object] | None] = mapped_column(JSON)
    completeness_score: Mapped[int] = mapped_column(Integer, nullable=False)
    completeness_breakdown: Mapped[dict[str, int]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    changes: Mapped[list[ListingChangeEvent]] = relationship(
        back_populates="snapshot",
        cascade="all, delete-orphan",
        foreign_keys="ListingChangeEvent.snapshot_id",
    )


class ListingChangeEvent(Base):
    __tablename__ = "listing_change_events"
    __table_args__ = (
        UniqueConstraint(
            "snapshot_id",
            "field_name",
            "change_type",
            name="uq_listing_change_events_snapshot_field_type",
        ),
        Index(
            "ix_listing_change_events_identity_observed", "marketplace_product_id", "observed_at"
        ),
        Index("ix_listing_change_events_product_observed", "product_id", "observed_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("listing_snapshots.id", ondelete="CASCADE"), nullable=False
    )
    previous_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("listing_snapshots.id", ondelete="SET NULL")
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
    field_name: Mapped[str] = mapped_column(String(100), nullable=False)
    change_type: Mapped[ListingChangeType] = mapped_column(
        enum_column(ListingChangeType, "listing_change_type"), nullable=False
    )
    old_value: Mapped[object | None] = mapped_column(JSON)
    new_value: Mapped[object | None] = mapped_column(JSON)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    snapshot: Mapped[ListingSnapshot] = relationship(
        back_populates="changes", foreign_keys=[snapshot_id]
    )
