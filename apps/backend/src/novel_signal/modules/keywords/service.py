from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, TypeVar

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from novel_signal.modules.keywords.errors import (
    KeywordConflictError,
    KeywordNotFoundError,
    KeywordValidationError,
)
from novel_signal.modules.keywords.models import Keyword, KeywordSource, TrackingTarget
from novel_signal.modules.keywords.repository import KeywordRepository
from novel_signal.modules.keywords.schemas import (
    BulkKeywordUpdate,
    KeywordCreate,
    KeywordUpdate,
    TrackingTargetCreate,
    TrackingTargetUpdate,
    normalize_keyword,
)
from novel_signal.modules.universe.models import CompetitorProduct, Product

EntityT = TypeVar("EntityT", Keyword, TrackingTarget)


class KeywordService:
    def __init__(self, session: Session) -> None:
        self.repository = KeywordRepository(session)

    def list_keywords(self, **filters: Any) -> tuple[list[Keyword], int]:
        return self.repository.list_keywords(**filters)

    def get_keyword(self, entity_id: uuid.UUID) -> Keyword:
        return self._require_keyword(entity_id)

    def create_keyword(self, payload: KeywordCreate) -> Keyword:
        normalized = normalize_keyword(payload.keyword_text)
        self._ensure_keyword_available(payload.marketplace, normalized)
        values = payload.model_dump(exclude={"sources"})
        entity = Keyword(**values, normalized_text=normalized)
        entity.sources = [KeywordSource(**source.model_dump()) for source in payload.sources]
        return self._persist(entity)

    def update_keyword(self, entity_id: uuid.UUID, payload: KeywordUpdate) -> Keyword:
        entity = self._require_keyword(entity_id)
        values = payload.model_dump(exclude_unset=True, exclude={"sources"})
        text = values.get("keyword_text", entity.keyword_text)
        marketplace = values.get("marketplace", entity.marketplace)
        normalized = normalize_keyword(text)
        self._ensure_keyword_available(marketplace, normalized, exclude_id=entity.id)
        values["normalized_text"] = normalized
        for key, value in values.items():
            setattr(entity, key, value)
        if "sources" in payload.model_fields_set and payload.sources is not None:
            existing = {(source.source_type, source.source_reference) for source in entity.sources}
            entity.sources.extend(
                KeywordSource(**source.model_dump())
                for source in payload.sources
                if (source.source_type, source.source_reference) not in existing
            )
        return self._persist(entity)

    def archive_keyword(self, entity_id: uuid.UUID) -> Keyword:
        return self._archive(self._require_keyword(entity_id), True)

    def restore_keyword(self, entity_id: uuid.UUID) -> Keyword:
        entity = self._require_keyword(entity_id)
        self._ensure_keyword_available(
            entity.marketplace, entity.normalized_text, exclude_id=entity.id
        )
        return self._archive(entity, False)

    def bulk_update(self, payload: BulkKeywordUpdate) -> int:
        entities = [self._require_keyword(entity_id) for entity_id in payload.keyword_ids]
        for entity in entities:
            if payload.tier is not None:
                entity.tier = payload.tier
            if payload.tracking_status is not None:
                entity.tracking_status = payload.tracking_status
        self._commit()
        return len(entities)

    def list_targets(self, **filters: Any) -> tuple[list[TrackingTarget], int]:
        return self.repository.list_targets(**filters)

    def get_target(self, entity_id: uuid.UUID) -> TrackingTarget:
        return self._require_target(entity_id)

    def create_target(self, payload: TrackingTargetCreate) -> TrackingTarget:
        self._validate_target(payload.keyword_id, payload.product_id, payload.competitor_product_id)
        self._ensure_target_available(
            payload.keyword_id, payload.product_id, payload.competitor_product_id
        )
        return self._persist(TrackingTarget(**payload.model_dump()))

    def update_target(self, entity_id: uuid.UUID, payload: TrackingTargetUpdate) -> TrackingTarget:
        entity = self._require_target(entity_id)
        values = payload.model_dump(exclude_unset=True)
        keyword_id = values.get("keyword_id", entity.keyword_id)
        product_id = values.get("product_id", entity.product_id)
        competitor_product_id = values.get("competitor_product_id", entity.competitor_product_id)
        if "product_id" in values and values["product_id"] is not None:
            competitor_product_id = None
        if "competitor_product_id" in values and values["competitor_product_id"] is not None:
            product_id = None
        self._validate_target(keyword_id, product_id, competitor_product_id)
        self._ensure_target_available(
            keyword_id, product_id, competitor_product_id, exclude_id=entity.id
        )
        values.update(product_id=product_id, competitor_product_id=competitor_product_id)
        for key, value in values.items():
            setattr(entity, key, value)
        return self._persist(entity)

    def archive_target(self, entity_id: uuid.UUID) -> TrackingTarget:
        return self._archive(self._require_target(entity_id), True)

    def restore_target(self, entity_id: uuid.UUID) -> TrackingTarget:
        entity = self._require_target(entity_id)
        self._validate_target(entity.keyword_id, entity.product_id, entity.competitor_product_id)
        self._ensure_target_available(
            entity.keyword_id, entity.product_id, entity.competitor_product_id, exclude_id=entity.id
        )
        return self._archive(entity, False)

    def _require_keyword(self, entity_id: uuid.UUID) -> Keyword:
        entity = self.repository.get_keyword(entity_id)
        if entity is None:
            raise KeywordNotFoundError("keyword not found")
        return entity

    def _require_target(self, entity_id: uuid.UUID) -> TrackingTarget:
        entity = self.repository.get_target(entity_id)
        if entity is None:
            raise KeywordNotFoundError(
                "tracking target not found", code="tracking_target_not_found"
            )
        return entity

    def _validate_target(
        self,
        keyword_id: uuid.UUID,
        product_id: uuid.UUID | None,
        competitor_product_id: uuid.UUID | None,
    ) -> None:
        if (product_id is None) == (competitor_product_id is None):
            raise KeywordValidationError(
                "exactly one target is required", code="tracking_target_invalid"
            )
        keyword = self._require_keyword(keyword_id)
        if keyword.archived_at is not None:
            raise KeywordValidationError("keyword is archived", code="archived_keyword")
        target: Product | CompetitorProduct | None
        if product_id is not None:
            target = self.repository.get_product(product_id)
        elif competitor_product_id is not None:
            target = self.repository.get_competitor_product(competitor_product_id)
        else:
            target = None
        if target is None:
            raise KeywordNotFoundError("target product not found", code="target_not_found")
        if target.archived_at is not None:
            raise KeywordValidationError("target product is archived", code="archived_target")

    def _ensure_keyword_available(
        self, marketplace: object, normalized: str, *, exclude_id: uuid.UUID | None = None
    ) -> None:
        if self.repository.keyword_identity_exists(marketplace, normalized, exclude_id=exclude_id):
            raise KeywordConflictError(
                "an active keyword with this normalized text already exists",
                code="keyword_duplicate",
            )

    def _ensure_target_available(
        self,
        keyword_id: uuid.UUID,
        product_id: uuid.UUID | None,
        competitor_product_id: uuid.UUID | None,
        *,
        exclude_id: uuid.UUID | None = None,
    ) -> None:
        if self.repository.target_exists(
            keyword_id, product_id, competitor_product_id, exclude_id=exclude_id
        ):
            raise KeywordConflictError(
                "an equivalent active tracking target already exists",
                code="tracking_target_duplicate",
            )

    def _persist(self, entity: EntityT) -> EntityT:
        self.repository.add(entity)
        self._commit()
        return entity

    def _archive(self, entity: EntityT, archived: bool) -> EntityT:
        entity.archived_at = datetime.now(UTC) if archived else None
        return self._persist(entity)

    def _commit(self) -> None:
        try:
            self.repository.commit()
        except IntegrityError as error:
            self.repository.rollback()
            raise KeywordConflictError(
                "operation conflicts with existing keyword configuration"
            ) from error
