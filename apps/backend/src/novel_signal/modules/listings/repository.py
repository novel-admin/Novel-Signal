from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from novel_signal.modules.listings.models import (
    ListingChangeEvent,
    ListingChangeType,
    ListingSnapshot,
)
from novel_signal.modules.universe.models import CompetitorProduct, Marketplace, Product


class ListingRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def mappings(
        self, marketplace: Marketplace, identity: str
    ) -> tuple[uuid.UUID | None, uuid.UUID | None]:
        owned = self.session.scalar(
            select(Product.id).where(
                Product.marketplace == marketplace,
                Product.marketplace_product_id == identity,
                Product.archived_at.is_(None),
            )
        )
        competitor = self.session.scalar(
            select(CompetitorProduct.id).where(
                CompetitorProduct.marketplace == marketplace,
                CompetitorProduct.marketplace_product_id == identity,
                CompetitorProduct.archived_at.is_(None),
            )
        )
        return owned, competitor

    def by_key(self, key: str) -> ListingSnapshot | None:
        return self.session.scalar(
            select(ListingSnapshot).where(ListingSnapshot.ingestion_key == key)
        )

    def get(self, id: uuid.UUID) -> ListingSnapshot | None:
        return self.session.get(ListingSnapshot, id)

    def latest(
        self,
        *,
        product_id: uuid.UUID | None = None,
        competitor_product_id: uuid.UUID | None = None,
        marketplace_product_id: str | None = None,
        marketplace: Marketplace | None = None,
        before: datetime | None = None,
    ) -> ListingSnapshot | None:
        q = select(ListingSnapshot)
        if product_id:
            q = q.where(ListingSnapshot.product_id == product_id)
        elif competitor_product_id:
            q = q.where(ListingSnapshot.competitor_product_id == competitor_product_id)
        else:
            q = q.where(ListingSnapshot.marketplace_product_id == marketplace_product_id)
        if marketplace:
            q = q.where(ListingSnapshot.marketplace == marketplace)
        if before:
            q = q.where(ListingSnapshot.captured_at < before)
        return self.session.scalar(q.order_by(ListingSnapshot.captured_at.desc()).limit(1))

    def snapshots(
        self,
        *,
        limit: int,
        offset: int,
        product_id: uuid.UUID | None = None,
        competitor_product_id: uuid.UUID | None = None,
        marketplace_product_id: str | None = None,
        marketplace: Marketplace | None = None,
        from_at: datetime | None = None,
        to_at: datetime | None = None,
        ascending: bool = False,
    ) -> tuple[list[ListingSnapshot], int]:
        q: Select[tuple[ListingSnapshot]] = select(ListingSnapshot)
        conditions = []
        if product_id:
            conditions.append(ListingSnapshot.product_id == product_id)
        if competitor_product_id:
            conditions.append(ListingSnapshot.competitor_product_id == competitor_product_id)
        if marketplace_product_id:
            conditions.append(ListingSnapshot.marketplace_product_id == marketplace_product_id)
        if marketplace:
            conditions.append(ListingSnapshot.marketplace == marketplace)
        if from_at:
            conditions.append(ListingSnapshot.captured_at >= from_at)
        if to_at:
            conditions.append(ListingSnapshot.captured_at <= to_at)
        q = q.where(*conditions)
        total = self.session.scalar(select(func.count()).select_from(q.subquery())) or 0
        order = (
            ListingSnapshot.captured_at.asc() if ascending else ListingSnapshot.captured_at.desc()
        )
        return list(self.session.scalars(q.order_by(order).limit(limit).offset(offset))), total

    def changes(
        self,
        *,
        limit: int,
        offset: int,
        product_id: uuid.UUID | None = None,
        competitor_product_id: uuid.UUID | None = None,
        marketplace_product_id: str | None = None,
        field_name: str | None = None,
        change_type: ListingChangeType | None = None,
        from_at: datetime | None = None,
        to_at: datetime | None = None,
    ) -> tuple[list[ListingChangeEvent], int]:
        q = select(ListingChangeEvent)
        c = []
        if product_id:
            c.append(ListingChangeEvent.product_id == product_id)
        if competitor_product_id:
            c.append(ListingChangeEvent.competitor_product_id == competitor_product_id)
        if marketplace_product_id:
            c.append(ListingChangeEvent.marketplace_product_id == marketplace_product_id)
        if field_name:
            c.append(ListingChangeEvent.field_name == field_name)
        if change_type:
            c.append(ListingChangeEvent.change_type == change_type)
        if from_at:
            c.append(ListingChangeEvent.observed_at >= from_at)
        if to_at:
            c.append(ListingChangeEvent.observed_at <= to_at)
        q = q.where(*c)
        total = self.session.scalar(select(func.count()).select_from(q.subquery())) or 0
        return list(
            self.session.scalars(
                q.order_by(ListingChangeEvent.observed_at.desc()).limit(limit).offset(offset)
            )
        ), total
