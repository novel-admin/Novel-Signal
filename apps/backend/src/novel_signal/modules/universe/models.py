from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    func,
    text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from novel_signal.db import Base

if TYPE_CHECKING:
    from novel_signal.modules.keywords.models import TrackingTarget


def utc_now() -> datetime:
    return datetime.now(UTC)


class PositioningTier(StrEnum):
    PREMIUM = "premium"
    MID = "mid"
    VALUE = "value"
    UNKNOWN = "unknown"


class TrackingTier(StrEnum):
    T1 = "T1"
    T2 = "T2"
    T3 = "T3"


class Marketplace(StrEnum):
    AMAZON_IN = "amazon_in"


class BattleCardStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"


def enum_column(enum_class: type[StrEnum], name: str) -> SAEnum:
    return SAEnum(
        enum_class,
        name=name,
        values_callable=lambda members: [member.value for member in members],
        validate_strings=True,
    )


class TimestampedArchiveMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        server_default=func.now(),
        nullable=False,
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Competitor(TimestampedArchiveMixin, Base):
    __tablename__ = "competitors"
    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),
        CheckConstraint(
            "threat_rating IS NULL OR threat_rating BETWEEN 1 AND 5",
            name="threat_rating_range",
        ),
        CheckConstraint(
            "amazon_store_url IS NULL OR length(trim(amazon_store_url)) > 0",
            name="amazon_store_url_not_blank",
        ),
        CheckConstraint(
            "amazon_seller_id IS NULL OR length(trim(amazon_seller_id)) > 0",
            name="amazon_seller_id_not_blank",
        ),
        CheckConstraint(
            "category_presence IS NULL OR length(trim(category_presence)) > 0",
            name="category_presence_not_blank",
        ),
        Index(
            "uq_competitors_normalized_active_name",
            func.lower(func.btrim(text("name"))),
            unique=True,
            postgresql_where=text("archived_at IS NULL"),
            sqlite_where=text("archived_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    parent_company: Mapped[str | None] = mapped_column(String(255))
    amazon_store_url: Mapped[str | None] = mapped_column(String(2048))
    amazon_seller_id: Mapped[str | None] = mapped_column(String(255))
    category_presence: Mapped[str | None] = mapped_column(Text)
    positioning_tier: Mapped[PositioningTier] = mapped_column(
        enum_column(PositioningTier, "positioning_tier"),
        default=PositioningTier.UNKNOWN,
        server_default=PositioningTier.UNKNOWN.value,
        nullable=False,
    )
    threat_rating: Mapped[int | None] = mapped_column(SmallInteger)
    analyst_owner: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)

    competitor_products: Mapped[list[CompetitorProduct]] = relationship(
        back_populates="competitor", passive_deletes=True
    )


class Product(TimestampedArchiveMixin, Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("length(trim(internal_sku)) > 0", name="internal_sku_not_blank"),
        CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),
        CheckConstraint("length(trim(brand)) > 0", name="brand_not_blank"),
        CheckConstraint("length(trim(category)) > 0", name="category_not_blank"),
        CheckConstraint(
            "marketplace_product_id IS NULL OR length(trim(marketplace_product_id)) > 0",
            name="marketplace_product_id_not_blank",
        ),
        CheckConstraint(
            "pack_quantity IS NULL OR pack_quantity > 0", name="pack_quantity_positive"
        ),
        Index("ix_products_marketplace_product_id", "marketplace", "marketplace_product_id"),
        Index("ix_products_archived_at", "archived_at"),
        Index(
            "uq_products_active_internal_sku",
            "internal_sku",
            unique=True,
            postgresql_where=text("archived_at IS NULL"),
            sqlite_where=text("archived_at IS NULL"),
        ),
        Index(
            "uq_products_active_marketplace_identity",
            "marketplace",
            "marketplace_product_id",
            unique=True,
            postgresql_where=text("archived_at IS NULL AND marketplace_product_id IS NOT NULL"),
            sqlite_where=text("archived_at IS NULL AND marketplace_product_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    internal_sku: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    brand: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(255), nullable=False)
    marketplace: Mapped[Marketplace] = mapped_column(
        enum_column(Marketplace, "marketplace"), nullable=False
    )
    marketplace_product_id: Mapped[str | None] = mapped_column(String(255))
    product_url: Mapped[str | None] = mapped_column(String(2048))
    pack_quantity: Mapped[int | None] = mapped_column(Integer)
    pack_unit: Mapped[str | None] = mapped_column(String(50))
    tracking_tier: Mapped[TrackingTier] = mapped_column(
        enum_column(TrackingTier, "tracking_tier"), nullable=False
    )

    battle_cards: Mapped[list[BattleCard]] = relationship(
        back_populates="product", passive_deletes=True
    )
    tracking_targets: Mapped[list[TrackingTarget]] = relationship(
        back_populates="product", passive_deletes=True
    )


class CompetitorProduct(TimestampedArchiveMixin, Base):
    __tablename__ = "competitor_products"
    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),
        CheckConstraint("length(trim(brand)) > 0", name="brand_not_blank"),
        CheckConstraint("length(trim(category)) > 0", name="category_not_blank"),
        CheckConstraint(
            "marketplace_product_id IS NULL OR length(trim(marketplace_product_id)) > 0",
            name="marketplace_product_id_not_blank",
        ),
        CheckConstraint(
            "pack_quantity IS NULL OR pack_quantity > 0", name="pack_quantity_positive"
        ),
        Index(
            "ix_competitor_products_marketplace_product_id",
            "marketplace",
            "marketplace_product_id",
        ),
        Index("ix_competitor_products_competitor_id", "competitor_id"),
        Index("ix_competitor_products_archived_at", "archived_at"),
        Index(
            "uq_competitor_products_active_marketplace_identity",
            "marketplace",
            "marketplace_product_id",
            unique=True,
            postgresql_where=text("archived_at IS NULL AND marketplace_product_id IS NOT NULL"),
            sqlite_where=text("archived_at IS NULL AND marketplace_product_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    competitor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("competitors.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    brand: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(255), nullable=False)
    marketplace: Mapped[Marketplace] = mapped_column(
        enum_column(Marketplace, "marketplace"), nullable=False
    )
    marketplace_product_id: Mapped[str | None] = mapped_column(String(255))
    product_url: Mapped[str | None] = mapped_column(String(2048))
    pack_quantity: Mapped[int | None] = mapped_column(Integer)
    pack_unit: Mapped[str | None] = mapped_column(String(50))
    tracking_tier: Mapped[TrackingTier] = mapped_column(
        enum_column(TrackingTier, "tracking_tier"), nullable=False
    )

    competitor: Mapped[Competitor] = relationship(back_populates="competitor_products")
    battle_card_items: Mapped[list[BattleCardItem]] = relationship(
        back_populates="competitor_product", passive_deletes=True
    )
    tracking_targets: Mapped[list[TrackingTarget]] = relationship(
        back_populates="competitor_product", passive_deletes=True
    )


class BattleCard(TimestampedArchiveMixin, Base):
    __tablename__ = "battle_cards"
    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),
        Index("ix_battle_cards_product_id", "product_id"),
        Index("ix_battle_cards_archived_at", "archived_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[BattleCardStatus] = mapped_column(
        enum_column(BattleCardStatus, "battle_card_status"),
        default=BattleCardStatus.DRAFT,
        server_default=BattleCardStatus.DRAFT.value,
        nullable=False,
    )
    comparison_notes: Mapped[str | None] = mapped_column(Text)

    product: Mapped[Product] = relationship(back_populates="battle_cards")
    items: Mapped[list[BattleCardItem]] = relationship(
        back_populates="battle_card", passive_deletes=True
    )


class BattleCardItem(TimestampedArchiveMixin, Base):
    __tablename__ = "battle_card_items"
    __table_args__ = (
        CheckConstraint(
            "priority_order IS NULL OR priority_order >= 0", name="priority_order_non_negative"
        ),
        Index("ix_battle_card_items_battle_card_id", "battle_card_id"),
        Index("ix_battle_card_items_competitor_product_id", "competitor_product_id"),
        Index("ix_battle_card_items_archived_at", "archived_at"),
        Index(
            "uq_battle_card_items_active_mapping",
            "battle_card_id",
            "competitor_product_id",
            unique=True,
            postgresql_where=text("archived_at IS NULL"),
            sqlite_where=text("archived_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    battle_card_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("battle_cards.id", ondelete="RESTRICT"), nullable=False
    )
    competitor_product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("competitor_products.id", ondelete="RESTRICT"), nullable=False
    )
    priority_order: Mapped[int | None] = mapped_column(Integer)
    same_pack_basis: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    same_price_band: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    same_category: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    same_use_case: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

    battle_card: Mapped[BattleCard] = relationship(back_populates="items")
    competitor_product: Mapped[CompetitorProduct] = relationship(back_populates="battle_card_items")
