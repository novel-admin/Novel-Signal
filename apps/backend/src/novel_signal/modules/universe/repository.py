from __future__ import annotations

import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.sql.elements import ColumnElement

from novel_signal.modules.universe.models import (
    BattleCard,
    BattleCardItem,
    Competitor,
    CompetitorProduct,
    Product,
)


class UniverseRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_competitors(
        self,
        *,
        include_archived: bool,
        limit: int,
        offset: int,
        search: str | None = None,
        positioning_tier: object | None = None,
        category_presence: str | None = None,
    ) -> tuple[list[Competitor], int]:
        filters: list[ColumnElement[bool]] = (
            [] if include_archived else [Competitor.archived_at.is_(None)]
        )
        if search:
            pattern = f"%{search}%"
            filters.append(
                or_(Competitor.name.ilike(pattern), Competitor.parent_company.ilike(pattern))
            )
        if positioning_tier:
            filters.append(Competitor.positioning_tier == positioning_tier)
        if category_presence:
            filters.append(Competitor.category_presence.ilike(f"%{category_presence}%"))
        items = list(
            self.session.scalars(
                select(Competitor)
                .where(*filters)
                .order_by(Competitor.name)
                .limit(limit)
                .offset(offset)
            )
        )
        total = self.session.scalar(select(func.count()).select_from(Competitor).where(*filters))
        return items, total or 0

    def get_competitor(self, entity_id: uuid.UUID) -> Competitor | None:
        return self.session.get(Competitor, entity_id)

    def list_products(
        self,
        *,
        include_archived: bool,
        limit: int,
        offset: int,
        internal_sku: str | None = None,
        brand: str | None = None,
        category: str | None = None,
        marketplace: object | None = None,
        tracking_tier: object | None = None,
    ) -> tuple[list[Product], int]:
        filters: list[ColumnElement[bool]] = (
            [] if include_archived else [Product.archived_at.is_(None)]
        )
        if internal_sku:
            filters.append(Product.internal_sku.ilike(f"%{internal_sku}%"))
        if brand:
            filters.append(Product.brand.ilike(f"%{brand}%"))
        if category:
            filters.append(Product.category.ilike(f"%{category}%"))
        if marketplace:
            filters.append(Product.marketplace == marketplace)
        if tracking_tier:
            filters.append(Product.tracking_tier == tracking_tier)
        items = list(
            self.session.scalars(
                select(Product).where(*filters).order_by(Product.name).limit(limit).offset(offset)
            )
        )
        total = self.session.scalar(select(func.count()).select_from(Product).where(*filters))
        return items, total or 0

    def get_product(self, entity_id: uuid.UUID) -> Product | None:
        return self.session.get(Product, entity_id)

    def list_competitor_products(
        self,
        *,
        include_archived: bool,
        limit: int,
        offset: int,
        competitor_id: uuid.UUID | None = None,
        brand: str | None = None,
        category: str | None = None,
        marketplace: object | None = None,
        tracking_tier: object | None = None,
    ) -> tuple[list[CompetitorProduct], int]:
        filters: list[ColumnElement[bool]] = (
            [] if include_archived else [CompetitorProduct.archived_at.is_(None)]
        )
        if competitor_id:
            filters.append(CompetitorProduct.competitor_id == competitor_id)
        if brand:
            filters.append(CompetitorProduct.brand.ilike(f"%{brand}%"))
        if category:
            filters.append(CompetitorProduct.category.ilike(f"%{category}%"))
        if marketplace:
            filters.append(CompetitorProduct.marketplace == marketplace)
        if tracking_tier:
            filters.append(CompetitorProduct.tracking_tier == tracking_tier)
        items = list(
            self.session.scalars(
                select(CompetitorProduct)
                .where(*filters)
                .order_by(CompetitorProduct.name)
                .limit(limit)
                .offset(offset)
            )
        )
        total = self.session.scalar(
            select(func.count()).select_from(CompetitorProduct).where(*filters)
        )
        return items, total or 0

    def get_competitor_product(self, entity_id: uuid.UUID) -> CompetitorProduct | None:
        return self.session.get(CompetitorProduct, entity_id)

    def list_battle_cards(
        self,
        *,
        include_archived: bool,
        limit: int,
        offset: int,
        product_id: uuid.UUID | None = None,
        status: object | None = None,
    ) -> tuple[list[BattleCard], int]:
        filters: list[ColumnElement[bool]] = (
            [] if include_archived else [BattleCard.archived_at.is_(None)]
        )
        if product_id:
            filters.append(BattleCard.product_id == product_id)
        if status:
            filters.append(BattleCard.status == status)
        items = list(
            self.session.scalars(
                select(BattleCard)
                .options(
                    selectinload(BattleCard.product),
                    selectinload(BattleCard.items).selectinload(BattleCardItem.competitor_product),
                )
                .where(*filters)
                .order_by(BattleCard.name)
                .limit(limit)
                .offset(offset)
            )
        )
        total = self.session.scalar(select(func.count()).select_from(BattleCard).where(*filters))
        return items, total or 0

    def get_battle_card(self, entity_id: uuid.UUID) -> BattleCard | None:
        return self.session.scalar(
            select(BattleCard)
            .options(
                selectinload(BattleCard.product),
                selectinload(BattleCard.items).selectinload(BattleCardItem.competitor_product),
            )
            .where(BattleCard.id == entity_id)
        )

    def list_battle_card_items(
        self,
        *,
        include_archived: bool,
        limit: int,
        offset: int,
        battle_card_id: uuid.UUID | None = None,
        competitor_product_id: uuid.UUID | None = None,
    ) -> tuple[list[BattleCardItem], int]:
        filters: list[ColumnElement[bool]] = (
            [] if include_archived else [BattleCardItem.archived_at.is_(None)]
        )
        if battle_card_id:
            filters.append(BattleCardItem.battle_card_id == battle_card_id)
        if competitor_product_id:
            filters.append(BattleCardItem.competitor_product_id == competitor_product_id)
        query = (
            select(BattleCardItem)
            .options(selectinload(BattleCardItem.competitor_product))
            .where(*filters)
        )
        items = list(
            self.session.scalars(
                query.order_by(BattleCardItem.priority_order, BattleCardItem.created_at)
                .limit(limit)
                .offset(offset)
            )
        )
        total = self.session.scalar(
            select(func.count()).select_from(BattleCardItem).where(*filters)
        )
        return items, total or 0

    def get_battle_card_item(self, entity_id: uuid.UUID) -> BattleCardItem | None:
        return self.session.scalar(
            select(BattleCardItem)
            .options(selectinload(BattleCardItem.competitor_product))
            .where(BattleCardItem.id == entity_id)
        )

    def active_competitor_name_exists(
        self, name: str, *, exclude_id: uuid.UUID | None = None
    ) -> bool:
        query = select(Competitor.id).where(
            Competitor.archived_at.is_(None),
            func.lower(func.btrim(Competitor.name)) == name.strip().lower(),
        )
        if exclude_id:
            query = query.where(Competitor.id != exclude_id)
        return self.session.scalar(query.limit(1)) is not None

    def active_product_sku_exists(self, sku: str, *, exclude_id: uuid.UUID | None = None) -> bool:
        query = select(Product.id).where(Product.archived_at.is_(None), Product.internal_sku == sku)
        if exclude_id:
            query = query.where(Product.id != exclude_id)
        return self.session.scalar(query.limit(1)) is not None

    def active_product_identity_exists(
        self, marketplace: object, identity: str | None, *, exclude_id: uuid.UUID | None = None
    ) -> bool:
        if identity is None:
            return False
        query = select(Product.id).where(
            Product.archived_at.is_(None),
            Product.marketplace == marketplace,
            Product.marketplace_product_id == identity,
        )
        if exclude_id:
            query = query.where(Product.id != exclude_id)
        return self.session.scalar(query.limit(1)) is not None

    def active_competitor_product_identity_exists(
        self,
        competitor_id: uuid.UUID,
        marketplace: object,
        identity: str | None,
        *,
        exclude_id: uuid.UUID | None = None,
    ) -> bool:
        if identity is None:
            return False
        query = select(CompetitorProduct.id).where(
            CompetitorProduct.archived_at.is_(None),
            CompetitorProduct.competitor_id == competitor_id,
            CompetitorProduct.marketplace == marketplace,
            CompetitorProduct.marketplace_product_id == identity,
        )
        if exclude_id:
            query = query.where(CompetitorProduct.id != exclude_id)
        return self.session.scalar(query.limit(1)) is not None

    def active_battle_card_item_exists(
        self,
        battle_card_id: uuid.UUID,
        competitor_product_id: uuid.UUID,
        *,
        exclude_id: uuid.UUID | None = None,
    ) -> bool:
        query = select(BattleCardItem.id).where(
            BattleCardItem.archived_at.is_(None),
            BattleCardItem.battle_card_id == battle_card_id,
            BattleCardItem.competitor_product_id == competitor_product_id,
        )
        if exclude_id:
            query = query.where(BattleCardItem.id != exclude_id)
        return self.session.scalar(query.limit(1)) is not None

    def add(self, entity: object) -> None:
        self.session.add(entity)

    def flush(self) -> None:
        self.session.flush()

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()
