from __future__ import annotations

import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.sql.elements import ColumnElement

from novel_signal.modules.keywords.models import (
    Keyword,
    KeywordSource,
    KeywordTrackingStatus,
    TrackingTarget,
)
from novel_signal.modules.universe.models import CompetitorProduct, Product, TrackingTier


class KeywordRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_keywords(
        self,
        *,
        include_archived: bool,
        limit: int,
        offset: int,
        search: str | None = None,
        source: object | None = None,
        tier: object | None = None,
        tracking_status: object | None = None,
        intent_cluster: object | None = None,
        marketplace: object | None = None,
        category: str | None = None,
        priority_only: bool = False,
    ) -> tuple[list[Keyword], int]:
        filters: list[ColumnElement[bool]] = (
            [] if include_archived else [Keyword.archived_at.is_(None)]
        )
        if search:
            filters.append(
                or_(
                    Keyword.keyword_text.ilike(f"%{search}%"),
                    Keyword.normalized_text.ilike(f"%{search}%"),
                )
            )
        if tier:
            filters.append(Keyword.tier == tier)
        if tracking_status:
            filters.append(Keyword.tracking_status == tracking_status)
        if intent_cluster:
            filters.append(Keyword.intent_cluster == intent_cluster)
        if marketplace:
            filters.append(Keyword.marketplace == marketplace)
        if category:
            filters.append(Keyword.category.ilike(f"%{category}%"))
        if priority_only:
            filters.extend(
                [
                    Keyword.tier == TrackingTier.T1,
                    Keyword.tracking_status == KeywordTrackingStatus.ACTIVE,
                    Keyword.archived_at.is_(None),
                ]
            )
        query = select(Keyword).options(selectinload(Keyword.sources)).where(*filters)
        count_query = (
            select(func.count(func.distinct(Keyword.id))).select_from(Keyword).where(*filters)
        )
        if source:
            query = query.join(Keyword.sources).where(KeywordSource.source_type == source)
            count_query = count_query.join(Keyword.sources).where(
                KeywordSource.source_type == source
            )
        items = list(
            self.session.scalars(
                query.order_by(Keyword.keyword_text).limit(limit).offset(offset)
            ).unique()
        )
        return items, self.session.scalar(count_query) or 0

    def get_keyword(self, entity_id: uuid.UUID) -> Keyword | None:
        return self.session.scalar(
            select(Keyword).options(selectinload(Keyword.sources)).where(Keyword.id == entity_id)
        )

    def get_keyword_by_identity(self, marketplace: object, normalized: str) -> Keyword | None:
        return self.session.scalar(
            select(Keyword)
            .options(selectinload(Keyword.sources))
            .where(
                Keyword.archived_at.is_(None),
                Keyword.marketplace == marketplace,
                Keyword.normalized_text == normalized,
            )
        )

    def list_targets(
        self,
        *,
        include_archived: bool,
        limit: int,
        offset: int,
        keyword_id: uuid.UUID | None = None,
        product_id: uuid.UUID | None = None,
        competitor_product_id: uuid.UUID | None = None,
        enabled: bool | None = None,
        cadence_minutes: int | None = None,
    ) -> tuple[list[TrackingTarget], int]:
        filters: list[ColumnElement[bool]] = (
            [] if include_archived else [TrackingTarget.archived_at.is_(None)]
        )
        if keyword_id:
            filters.append(TrackingTarget.keyword_id == keyword_id)
        if product_id:
            filters.append(TrackingTarget.product_id == product_id)
        if competitor_product_id:
            filters.append(TrackingTarget.competitor_product_id == competitor_product_id)
        if enabled is not None:
            filters.append(TrackingTarget.enabled == enabled)
        if cadence_minutes:
            filters.append(TrackingTarget.cadence_minutes == cadence_minutes)
        items = list(
            self.session.scalars(
                select(TrackingTarget)
                .where(*filters)
                .order_by(TrackingTarget.created_at)
                .limit(limit)
                .offset(offset)
            )
        )
        total = (
            self.session.scalar(select(func.count()).select_from(TrackingTarget).where(*filters))
            or 0
        )
        return items, total

    def get_target(self, entity_id: uuid.UUID) -> TrackingTarget | None:
        return self.session.get(TrackingTarget, entity_id)

    def get_product(self, entity_id: uuid.UUID) -> Product | None:
        return self.session.get(Product, entity_id)

    def get_competitor_product(self, entity_id: uuid.UUID) -> CompetitorProduct | None:
        return self.session.get(CompetitorProduct, entity_id)

    def keyword_identity_exists(
        self, marketplace: object, normalized: str, *, exclude_id: uuid.UUID | None = None
    ) -> bool:
        query = select(Keyword.id).where(
            Keyword.archived_at.is_(None),
            Keyword.marketplace == marketplace,
            Keyword.normalized_text == normalized,
        )
        if exclude_id:
            query = query.where(Keyword.id != exclude_id)
        return self.session.scalar(query.limit(1)) is not None

    def target_exists(
        self,
        keyword_id: uuid.UUID,
        product_id: uuid.UUID | None,
        competitor_product_id: uuid.UUID | None,
        *,
        exclude_id: uuid.UUID | None = None,
    ) -> bool:
        query = select(TrackingTarget.id).where(
            TrackingTarget.archived_at.is_(None), TrackingTarget.keyword_id == keyword_id
        )
        query = (
            query.where(TrackingTarget.product_id == product_id)
            if product_id
            else query.where(TrackingTarget.competitor_product_id == competitor_product_id)
        )
        if exclude_id:
            query = query.where(TrackingTarget.id != exclude_id)
        return self.session.scalar(query.limit(1)) is not None

    def add(self, entity: object) -> None:
        self.session.add(entity)

    def flush(self) -> None:
        self.session.flush()

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()
