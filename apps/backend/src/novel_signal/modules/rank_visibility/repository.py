from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, selectinload

from novel_signal.modules.keywords.models import Keyword
from novel_signal.modules.rank_visibility.models import (
    BadgeEvent,
    BadgeEventType,
    BadgeType,
    DeviceProfile,
    NewEntrantEvent,
    SerpCapture,
    SerpResult,
)
from novel_signal.modules.universe.models import CompetitorProduct, Marketplace, Product


class RankVisibilityRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def capture_by_ingestion_key(self, key: str) -> SerpCapture | None:
        return self.session.scalar(select(SerpCapture).where(SerpCapture.ingestion_key == key))

    def capture(self, capture_id: uuid.UUID, *, with_results: bool = False) -> SerpCapture | None:
        query = select(SerpCapture).where(SerpCapture.id == capture_id)
        if with_results:
            query = query.options(selectinload(SerpCapture.results))
        return self.session.scalar(query)

    def keyword_exists(self, keyword_id: uuid.UUID) -> bool:
        from novel_signal.modules.keywords.models import Keyword

        return self.session.scalar(select(Keyword.id).where(Keyword.id == keyword_id)) is not None

    def product_mappings(
        self, marketplace: Marketplace, marketplace_ids: set[str]
    ) -> tuple[dict[str, uuid.UUID], dict[str, uuid.UUID]]:
        if not marketplace_ids:
            return {}, {}
        owned = self.session.execute(
            select(Product.marketplace_product_id, Product.id).where(
                Product.marketplace == marketplace,
                Product.marketplace_product_id.in_(marketplace_ids),
                Product.archived_at.is_(None),
            )
        ).all()
        competitors = self.session.execute(
            select(CompetitorProduct.marketplace_product_id, CompetitorProduct.id).where(
                CompetitorProduct.marketplace == marketplace,
                CompetitorProduct.marketplace_product_id.in_(marketplace_ids),
                CompetitorProduct.archived_at.is_(None),
            )
        ).all()
        return (
            {str(key): value for key, value in owned if key is not None},
            {str(key): value for key, value in competitors if key is not None},
        )

    def previous_result(
        self, capture: SerpCapture, marketplace_product_id: str
    ) -> SerpResult | None:
        return self.session.scalar(
            select(SerpResult)
            .join(SerpCapture)
            .where(
                SerpCapture.keyword_id == capture.keyword_id,
                SerpCapture.marketplace == capture.marketplace,
                SerpCapture.geo_code == capture.geo_code,
                SerpCapture.device_profile == capture.device_profile,
                SerpCapture.captured_at < capture.captured_at,
                SerpResult.marketplace_product_id == marketplace_product_id,
            )
            .order_by(SerpCapture.captured_at.desc(), SerpResult.absolute_position)
            .limit(1)
        )

    def entrant_exists(self, capture: SerpCapture, marketplace_product_id: str) -> bool:
        return (
            self.session.scalar(
                select(NewEntrantEvent.id).where(
                    NewEntrantEvent.keyword_id == capture.keyword_id,
                    NewEntrantEvent.marketplace == capture.marketplace,
                    NewEntrantEvent.marketplace_product_id == marketplace_product_id,
                    NewEntrantEvent.geo_code == capture.geo_code,
                    NewEntrantEvent.device_profile == capture.device_profile,
                )
            )
            is not None
        )

    def list_captures(
        self,
        *,
        limit: int,
        offset: int,
        keyword_id: uuid.UUID | None,
        marketplace: Marketplace | None,
        geo_code: str | None,
        device_profile: DeviceProfile | None,
        from_at: datetime | None,
        to_at: datetime | None,
    ) -> tuple[list[SerpCapture], int]:
        query: Select[tuple[SerpCapture]] = select(SerpCapture)
        conditions = []
        if keyword_id:
            conditions.append(SerpCapture.keyword_id == keyword_id)
        if marketplace:
            conditions.append(SerpCapture.marketplace == marketplace)
        if geo_code:
            conditions.append(SerpCapture.geo_code == geo_code)
        if device_profile:
            conditions.append(SerpCapture.device_profile == device_profile)
        if from_at:
            conditions.append(SerpCapture.captured_at >= from_at)
        if to_at:
            conditions.append(SerpCapture.captured_at <= to_at)
        query = query.where(*conditions)
        total = self.session.scalar(select(func.count()).select_from(query.subquery())) or 0
        items = list(
            self.session.scalars(
                query.order_by(SerpCapture.captured_at.desc()).limit(limit).offset(offset)
            )
        )
        return items, total

    def result_history(
        self,
        *,
        keyword_id: uuid.UUID,
        product_id: uuid.UUID | None,
        competitor_product_id: uuid.UUID | None,
        marketplace_product_id: str | None,
        marketplace: Marketplace | None,
        geo_code: str | None,
        device_profile: DeviceProfile | None,
        from_at: datetime | None,
        to_at: datetime | None,
    ) -> list[tuple[SerpResult, SerpCapture]]:
        query = select(SerpResult, SerpCapture).join(SerpCapture)
        conditions = [SerpCapture.keyword_id == keyword_id]
        if product_id:
            conditions.append(SerpResult.product_id == product_id)
        elif competitor_product_id:
            conditions.append(SerpResult.competitor_product_id == competitor_product_id)
        else:
            conditions.append(SerpResult.marketplace_product_id == marketplace_product_id)
        if marketplace:
            conditions.append(SerpCapture.marketplace == marketplace)
        if geo_code:
            conditions.append(SerpCapture.geo_code == geo_code)
        if device_profile:
            conditions.append(SerpCapture.device_profile == device_profile)
        if from_at:
            conditions.append(SerpCapture.captured_at >= from_at)
        if to_at:
            conditions.append(SerpCapture.captured_at <= to_at)
        rows = self.session.execute(
            query.where(*conditions).order_by(SerpCapture.captured_at, SerpResult.absolute_position)
        ).all()
        return [(result, capture) for result, capture in rows]

    def identity_history(
        self,
        *,
        product_id: uuid.UUID | None,
        competitor_product_id: uuid.UUID | None,
        marketplace_product_id: str | None,
        marketplace: Marketplace | None,
        geo_code: str | None,
        device_profile: DeviceProfile | None,
        from_at: datetime | None,
        to_at: datetime | None,
    ) -> list[tuple[SerpResult, SerpCapture, Keyword]]:
        query = (
            select(SerpResult, SerpCapture, Keyword)
            .select_from(SerpResult)
            .join(SerpCapture, SerpCapture.id == SerpResult.capture_id)
            .join(Keyword, Keyword.id == SerpCapture.keyword_id)
        )
        conditions = []
        if product_id:
            conditions.append(SerpResult.product_id == product_id)
        elif competitor_product_id:
            conditions.append(SerpResult.competitor_product_id == competitor_product_id)
        else:
            conditions.append(SerpResult.marketplace_product_id == marketplace_product_id)
        if marketplace:
            conditions.append(SerpCapture.marketplace == marketplace)
        if geo_code:
            conditions.append(SerpCapture.geo_code == geo_code)
        if device_profile:
            conditions.append(SerpCapture.device_profile == device_profile)
        if from_at:
            conditions.append(SerpCapture.captured_at >= from_at)
        if to_at:
            conditions.append(SerpCapture.captured_at <= to_at)
        return [
            (result, capture, keyword)
            for result, capture, keyword in self.session.execute(
                query.where(*conditions).order_by(
                    SerpCapture.captured_at, SerpResult.absolute_position
                )
            ).all()
        ]

    def filtered_captures_with_results(
        self,
        *,
        marketplace: Marketplace,
        geo_code: str | None,
        device_profile: DeviceProfile | None,
        from_at: datetime | None,
        to_at: datetime | None,
    ) -> list[SerpCapture]:
        query = (
            select(SerpCapture)
            .options(selectinload(SerpCapture.results))
            .where(SerpCapture.marketplace == marketplace)
        )
        if geo_code:
            query = query.where(SerpCapture.geo_code == geo_code)
        if device_profile:
            query = query.where(SerpCapture.device_profile == device_profile)
        if from_at:
            query = query.where(SerpCapture.captured_at >= from_at)
        if to_at:
            query = query.where(SerpCapture.captured_at <= to_at)
        return list(
            self.session.scalars(query.order_by(SerpCapture.captured_at, SerpCapture.id)).unique()
        )

    def brand_results(
        self,
        *,
        capture_id: uuid.UUID | None,
        keyword_id: uuid.UUID | None,
        from_at: datetime | None,
        to_at: datetime | None,
    ) -> list[SerpResult]:
        query = select(SerpResult).join(SerpCapture).where(SerpResult.page_number == 1)
        if capture_id:
            query = query.where(SerpCapture.id == capture_id)
        if keyword_id:
            query = query.where(SerpCapture.keyword_id == keyword_id)
        if from_at:
            query = query.where(SerpCapture.captured_at >= from_at)
        if to_at:
            query = query.where(SerpCapture.captured_at <= to_at)
        return list(self.session.scalars(query))

    def list_badge_events(
        self,
        *,
        limit: int,
        offset: int,
        keyword_id: uuid.UUID | None,
        marketplace_product_id: str | None,
        badge_type: BadgeType | None,
        event_type: BadgeEventType | None,
        from_at: datetime | None,
        to_at: datetime | None,
    ) -> tuple[list[BadgeEvent], int]:
        query = select(BadgeEvent)
        conditions = []
        for condition in (
            BadgeEvent.keyword_id == keyword_id if keyword_id else None,
            BadgeEvent.marketplace_product_id == marketplace_product_id
            if marketplace_product_id
            else None,
            BadgeEvent.badge_type == badge_type if badge_type else None,
            BadgeEvent.event_type == event_type if event_type else None,
            BadgeEvent.observed_at >= from_at if from_at else None,
            BadgeEvent.observed_at <= to_at if to_at else None,
        ):
            if condition is not None:
                conditions.append(condition)
        query = query.where(*conditions)
        total = self.session.scalar(select(func.count()).select_from(query.subquery())) or 0
        return (
            list(
                self.session.scalars(
                    query.order_by(BadgeEvent.observed_at.desc()).limit(limit).offset(offset)
                )
            ),
            total,
        )

    def list_new_entrants(
        self,
        *,
        limit: int,
        offset: int,
        keyword_id: uuid.UUID | None,
        brand: str | None,
        mapped: bool | None,
        from_at: datetime | None,
        to_at: datetime | None,
    ) -> tuple[list[NewEntrantEvent], int]:
        query = select(NewEntrantEvent)
        conditions = []
        if keyword_id:
            conditions.append(NewEntrantEvent.keyword_id == keyword_id)
        if brand:
            conditions.append(func.lower(NewEntrantEvent.brand) == brand.lower())
        if mapped is True:
            conditions.append(
                (NewEntrantEvent.product_id.is_not(None))
                | (NewEntrantEvent.competitor_product_id.is_not(None))
            )
        elif mapped is False:
            conditions.extend(
                [
                    NewEntrantEvent.product_id.is_(None),
                    NewEntrantEvent.competitor_product_id.is_(None),
                ]
            )
        if from_at:
            conditions.append(NewEntrantEvent.first_seen_at >= from_at)
        if to_at:
            conditions.append(NewEntrantEvent.first_seen_at <= to_at)
        query = query.where(*conditions)
        total = self.session.scalar(select(func.count()).select_from(query.subquery())) or 0
        return (
            list(
                self.session.scalars(
                    query.order_by(NewEntrantEvent.first_seen_at.desc()).limit(limit).offset(offset)
                )
            ),
            total,
        )
