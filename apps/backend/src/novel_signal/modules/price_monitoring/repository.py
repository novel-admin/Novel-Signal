from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, selectinload

from novel_signal.modules.price_monitoring.models import (
    AvailabilityStatus,
    PriceChangeEvent,
    PriceEventType,
    PriceObservation,
    SellerOffer,
)
from novel_signal.modules.universe.models import CompetitorProduct, Marketplace, Product


class PriceRepository:
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

    def by_key(self, key: str) -> PriceObservation | None:
        return self.session.scalar(
            select(PriceObservation).where(PriceObservation.ingestion_key == key)
        )

    def get(self, id: uuid.UUID) -> PriceObservation | None:
        return self.session.scalar(
            select(PriceObservation)
            .options(selectinload(PriceObservation.offers))
            .where(PriceObservation.id == id)
        )

    def latest(
        self,
        *,
        product_id: uuid.UUID | None = None,
        competitor_product_id: uuid.UUID | None = None,
        marketplace_product_id: str | None = None,
        marketplace: Marketplace | None = None,
        geo_code: str | None = None,
        before: datetime | None = None,
    ) -> PriceObservation | None:
        q = select(PriceObservation).options(selectinload(PriceObservation.offers))
        if product_id:
            q = q.where(PriceObservation.product_id == product_id)
        elif competitor_product_id:
            q = q.where(PriceObservation.competitor_product_id == competitor_product_id)
        else:
            q = q.where(PriceObservation.marketplace_product_id == marketplace_product_id)
        if marketplace:
            q = q.where(PriceObservation.marketplace == marketplace)
        if geo_code is not None:
            q = q.where(PriceObservation.geo_code == geo_code)
        if before:
            q = q.where(PriceObservation.observed_at < before)
        return self.session.scalar(q.order_by(PriceObservation.observed_at.desc()).limit(1))

    def observations(
        self,
        *,
        limit: int,
        offset: int,
        product_id: uuid.UUID | None = None,
        competitor_product_id: uuid.UUID | None = None,
        marketplace_product_id: str | None = None,
        marketplace: Marketplace | None = None,
        geo_code: str | None = None,
        availability: AvailabilityStatus | None = None,
        from_at: datetime | None = None,
        to_at: datetime | None = None,
        ascending: bool = False,
    ) -> tuple[list[PriceObservation], int]:
        q: Select[tuple[PriceObservation]] = select(PriceObservation).options(
            selectinload(PriceObservation.offers)
        )
        c = []
        if product_id:
            c.append(PriceObservation.product_id == product_id)
        if competitor_product_id:
            c.append(PriceObservation.competitor_product_id == competitor_product_id)
        if marketplace_product_id:
            c.append(PriceObservation.marketplace_product_id == marketplace_product_id)
        if marketplace:
            c.append(PriceObservation.marketplace == marketplace)
        if geo_code is not None:
            c.append(PriceObservation.geo_code == geo_code)
        if availability:
            c.append(PriceObservation.availability_status == availability)
        if from_at:
            c.append(PriceObservation.observed_at >= from_at)
        if to_at:
            c.append(PriceObservation.observed_at <= to_at)
        q = q.where(*c)
        total = self.session.scalar(select(func.count()).select_from(q.subquery())) or 0
        order = (
            PriceObservation.observed_at.asc() if ascending else PriceObservation.observed_at.desc()
        )
        return list(self.session.scalars(q.order_by(order).limit(limit).offset(offset))), total

    def events(
        self,
        *,
        limit: int,
        offset: int,
        product_id: uuid.UUID | None = None,
        competitor_product_id: uuid.UUID | None = None,
        marketplace_product_id: str | None = None,
        event_type: PriceEventType | None = None,
        geo_code: str | None = None,
        from_at: datetime | None = None,
        to_at: datetime | None = None,
    ) -> tuple[list[PriceChangeEvent], int]:
        q = select(PriceChangeEvent)
        c = []
        if product_id:
            c.append(PriceChangeEvent.product_id == product_id)
        if competitor_product_id:
            c.append(PriceChangeEvent.competitor_product_id == competitor_product_id)
        if marketplace_product_id:
            c.append(PriceChangeEvent.marketplace_product_id == marketplace_product_id)
        if event_type:
            c.append(PriceChangeEvent.event_type == event_type)
        if geo_code is not None:
            c.append(PriceChangeEvent.geo_code == geo_code)
        if from_at:
            c.append(PriceChangeEvent.observed_at >= from_at)
        if to_at:
            c.append(PriceChangeEvent.observed_at <= to_at)
        q = q.where(*c)
        total = self.session.scalar(select(func.count()).select_from(q.subquery())) or 0
        return list(
            self.session.scalars(
                q.order_by(PriceChangeEvent.observed_at.desc()).limit(limit).offset(offset)
            )
        ), total

    def offers(self, observation_id: uuid.UUID) -> list[SellerOffer]:
        return list(
            self.session.scalars(
                select(SellerOffer)
                .where(SellerOffer.observation_id == observation_id)
                .order_by(SellerOffer.seller_name)
            )
        )
