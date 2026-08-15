from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from novel_signal.modules.universe.errors import (
    UniverseConflictError,
    UniverseNotFoundError,
    UniverseValidationError,
)
from novel_signal.modules.universe.models import (
    BattleCard,
    BattleCardItem,
    BattleCardStatus,
    Competitor,
    CompetitorProduct,
    Marketplace,
    PositioningTier,
    Product,
    TrackingTier,
)
from novel_signal.modules.universe.repository import UniverseRepository
from novel_signal.modules.universe.schemas import (
    BattleCardCreate,
    BattleCardItemCreate,
    BattleCardItemUpdate,
    BattleCardItemWrite,
    BattleCardUpdate,
    CompetitorCreate,
    CompetitorProductCreate,
    CompetitorProductUpdate,
    CompetitorUpdate,
    ProductCreate,
    ProductUpdate,
    validate_marketplace_product_id,
)


class Archivable(Protocol):
    archived_at: datetime | None


class UniverseService:
    def __init__(self, session: Session) -> None:
        self.repository = UniverseRepository(session)

    def list_competitors(
        self,
        *,
        include_archived: bool,
        limit: int,
        offset: int,
        search: str | None = None,
        positioning_tier: PositioningTier | None = None,
        category_presence: str | None = None,
    ) -> tuple[list[Competitor], int]:
        return self.repository.list_competitors(
            include_archived=include_archived,
            limit=limit,
            offset=offset,
            search=search,
            positioning_tier=positioning_tier,
            category_presence=category_presence,
        )

    def get_competitor(self, entity_id: uuid.UUID) -> Competitor:
        return self._require_competitor(entity_id)

    def create_competitor(self, payload: CompetitorCreate) -> Competitor:
        self._ensure_competitor_name_available(payload.name)
        return self._persist(Competitor(**payload.model_dump()))

    def update_competitor(self, entity_id: uuid.UUID, payload: CompetitorUpdate) -> Competitor:
        entity = self._require_competitor(entity_id)
        values = payload.model_dump(exclude_unset=True)
        if values.get("name") is not None:
            self._ensure_competitor_name_available(values["name"], exclude_id=entity.id)
        self._apply(entity, values)
        return self._persist(entity)

    def archive_competitor(self, entity_id: uuid.UUID) -> Competitor:
        return self._set_archive(self._require_competitor(entity_id), archived=True)

    def restore_competitor(self, entity_id: uuid.UUID) -> Competitor:
        entity = self._require_competitor(entity_id)
        self._ensure_competitor_name_available(entity.name, exclude_id=entity.id)
        return self._set_archive(entity, archived=False)

    def list_products(
        self,
        *,
        include_archived: bool,
        limit: int,
        offset: int,
        internal_sku: str | None = None,
        brand: str | None = None,
        category: str | None = None,
        marketplace: Marketplace | None = None,
        tracking_tier: TrackingTier | None = None,
    ) -> tuple[list[Product], int]:
        return self.repository.list_products(
            include_archived=include_archived,
            limit=limit,
            offset=offset,
            internal_sku=internal_sku,
            brand=brand,
            category=category,
            marketplace=marketplace,
            tracking_tier=tracking_tier,
        )

    def get_product(self, entity_id: uuid.UUID) -> Product:
        return self._require_product(entity_id)

    def create_product(self, payload: ProductCreate) -> Product:
        self._ensure_product_available(
            payload.internal_sku, payload.marketplace, payload.marketplace_product_id
        )
        return self._persist(Product(**payload.model_dump()))

    def update_product(self, entity_id: uuid.UUID, payload: ProductUpdate) -> Product:
        entity = self._require_product(entity_id)
        values = payload.model_dump(exclude_unset=True)
        marketplace = values.get("marketplace", entity.marketplace)
        identity = values.get("marketplace_product_id", entity.marketplace_product_id)
        validate_marketplace_product_id(marketplace, identity)
        self._ensure_product_available(
            values.get("internal_sku", entity.internal_sku),
            marketplace,
            identity,
            exclude_id=entity.id,
        )
        self._apply(entity, values)
        return self._persist(entity)

    def archive_product(self, entity_id: uuid.UUID) -> Product:
        return self._set_archive(self._require_product(entity_id), archived=True)

    def restore_product(self, entity_id: uuid.UUID) -> Product:
        entity = self._require_product(entity_id)
        self._ensure_product_available(
            entity.internal_sku,
            entity.marketplace,
            entity.marketplace_product_id,
            exclude_id=entity.id,
        )
        return self._set_archive(entity, archived=False)

    def list_competitor_products(
        self,
        *,
        include_archived: bool,
        limit: int,
        offset: int,
        competitor_id: uuid.UUID | None = None,
        brand: str | None = None,
        category: str | None = None,
        marketplace: Marketplace | None = None,
        tracking_tier: TrackingTier | None = None,
    ) -> tuple[list[CompetitorProduct], int]:
        return self.repository.list_competitor_products(
            include_archived=include_archived,
            limit=limit,
            offset=offset,
            competitor_id=competitor_id,
            brand=brand,
            category=category,
            marketplace=marketplace,
            tracking_tier=tracking_tier,
        )

    def get_competitor_product(self, entity_id: uuid.UUID) -> CompetitorProduct:
        return self._require_competitor_product(entity_id)

    def create_competitor_product(self, payload: CompetitorProductCreate) -> CompetitorProduct:
        self._require_active_competitor(payload.competitor_id)
        self._ensure_competitor_product_identity_available(
            payload.marketplace, payload.marketplace_product_id
        )
        return self._persist(CompetitorProduct(**payload.model_dump()))

    def update_competitor_product(
        self, entity_id: uuid.UUID, payload: CompetitorProductUpdate
    ) -> CompetitorProduct:
        entity = self._require_competitor_product(entity_id)
        values = payload.model_dump(exclude_unset=True)
        competitor_id = values.get("competitor_id", entity.competitor_id)
        self._require_active_competitor(competitor_id)
        marketplace = values.get("marketplace", entity.marketplace)
        identity = values.get("marketplace_product_id", entity.marketplace_product_id)
        validate_marketplace_product_id(marketplace, identity)
        self._ensure_competitor_product_identity_available(
            marketplace, identity, exclude_id=entity.id
        )
        self._apply(entity, values)
        return self._persist(entity)

    def archive_competitor_product(self, entity_id: uuid.UUID) -> CompetitorProduct:
        return self._set_archive(self._require_competitor_product(entity_id), archived=True)

    def restore_competitor_product(self, entity_id: uuid.UUID) -> CompetitorProduct:
        entity = self._require_competitor_product(entity_id)
        self._require_active_competitor(entity.competitor_id)
        self._ensure_competitor_product_identity_available(
            entity.marketplace,
            entity.marketplace_product_id,
            exclude_id=entity.id,
        )
        return self._set_archive(entity, archived=False)

    def list_battle_cards(
        self,
        *,
        include_archived: bool,
        limit: int,
        offset: int,
        product_id: uuid.UUID | None = None,
        status: BattleCardStatus | None = None,
    ) -> tuple[list[BattleCard], int]:
        return self.repository.list_battle_cards(
            include_archived=include_archived,
            limit=limit,
            offset=offset,
            product_id=product_id,
            status=status,
        )

    def get_battle_card(self, entity_id: uuid.UUID) -> BattleCard:
        return self._require_battle_card(entity_id)

    def create_battle_card(self, payload: BattleCardCreate) -> BattleCard:
        self._require_active_product(payload.product_id)
        battle_card = BattleCard(
            product_id=payload.product_id,
            name=payload.name,
            status=payload.status,
            comparison_notes=payload.comparison_notes,
        )
        self.repository.add(battle_card)
        self.repository.flush()
        self._sync_battle_card_items(battle_card, payload.items)
        self._commit()
        return self._require_battle_card(battle_card.id)

    def update_battle_card(self, entity_id: uuid.UUID, payload: BattleCardUpdate) -> BattleCard:
        battle_card = self._require_battle_card(entity_id)
        values = payload.model_dump(exclude_unset=True, exclude={"items"})
        product_id = values.get("product_id", battle_card.product_id)
        self._require_active_product(product_id)
        self._apply(battle_card, values)
        if "items" in payload.model_fields_set and payload.items is not None:
            self._require_active_battle_card(entity_id)
            self._sync_battle_card_items(battle_card, payload.items)
        self._commit()
        return self._require_battle_card(entity_id)

    def archive_battle_card(self, entity_id: uuid.UUID) -> BattleCard:
        self._set_archive(self._require_battle_card(entity_id), archived=True)
        return self._require_battle_card(entity_id)

    def restore_battle_card(self, entity_id: uuid.UUID) -> BattleCard:
        battle_card = self._require_battle_card(entity_id)
        self._require_active_product(battle_card.product_id)
        self._set_archive(battle_card, archived=False)
        return self._require_battle_card(entity_id)

    def list_battle_card_items(
        self,
        *,
        include_archived: bool,
        limit: int,
        offset: int,
        battle_card_id: uuid.UUID | None = None,
        competitor_product_id: uuid.UUID | None = None,
    ) -> tuple[list[BattleCardItem], int]:
        return self.repository.list_battle_card_items(
            include_archived=include_archived,
            limit=limit,
            offset=offset,
            battle_card_id=battle_card_id,
            competitor_product_id=competitor_product_id,
        )

    def get_battle_card_item(self, entity_id: uuid.UUID) -> BattleCardItem:
        return self._require_battle_card_item(entity_id)

    def create_battle_card_item(self, payload: BattleCardItemCreate) -> BattleCardItem:
        self._require_active_battle_card(payload.battle_card_id)
        self._require_active_competitor_product(payload.competitor_product_id)
        self._ensure_item_mapping_available(payload.battle_card_id, payload.competitor_product_id)
        entity = BattleCardItem(**payload.model_dump())
        self._persist(entity)
        return self._require_battle_card_item(entity.id)

    def update_battle_card_item(
        self, entity_id: uuid.UUID, payload: BattleCardItemUpdate
    ) -> BattleCardItem:
        entity = self._require_battle_card_item(entity_id)
        values = payload.model_dump(exclude_unset=True)
        battle_card_id = values.get("battle_card_id", entity.battle_card_id)
        competitor_product_id = values.get("competitor_product_id", entity.competitor_product_id)
        self._require_active_battle_card(battle_card_id)
        self._require_active_competitor_product(competitor_product_id)
        self._ensure_item_mapping_available(
            battle_card_id, competitor_product_id, exclude_id=entity.id
        )
        self._apply(entity, values)
        self._persist(entity)
        return self._require_battle_card_item(entity.id)

    def archive_battle_card_item(self, entity_id: uuid.UUID) -> BattleCardItem:
        entity = self._require_battle_card_item(entity_id)
        self._set_archive(entity, archived=True)
        return self._require_battle_card_item(entity_id)

    def restore_battle_card_item(self, entity_id: uuid.UUID) -> BattleCardItem:
        entity = self._require_battle_card_item(entity_id)
        self._require_active_battle_card(entity.battle_card_id)
        self._require_active_competitor_product(entity.competitor_product_id)
        self._ensure_item_mapping_available(
            entity.battle_card_id, entity.competitor_product_id, exclude_id=entity.id
        )
        self._set_archive(entity, archived=False)
        return self._require_battle_card_item(entity_id)

    def _sync_battle_card_items(
        self, battle_card: BattleCard, requested_items: list[BattleCardItemWrite]
    ) -> None:
        existing = {item.competitor_product_id: item for item in battle_card.items}
        requested_ids = {item.competitor_product_id for item in requested_items}
        for item in requested_items:
            self._require_active_competitor_product(item.competitor_product_id)
            values = item.model_dump(exclude={"competitor_product_id"})
            current = existing.get(item.competitor_product_id)
            if current is None:
                current = BattleCardItem(
                    battle_card=battle_card,
                    competitor_product_id=item.competitor_product_id,
                    **values,
                )
                self.repository.add(current)
            else:
                self._apply(current, values)
                current.archived_at = None
        for product_id, current in existing.items():
            if product_id not in requested_ids and current.archived_at is None:
                current.archived_at = datetime.now(UTC)
        self.repository.flush()

    def _require_competitor(self, entity_id: uuid.UUID) -> Competitor:
        entity = self.repository.get_competitor(entity_id)
        if entity is None:
            raise UniverseNotFoundError("competitor not found")
        return entity

    def _require_active_competitor(self, entity_id: uuid.UUID) -> Competitor:
        entity = self._require_competitor(entity_id)
        if entity.archived_at is not None:
            raise UniverseValidationError("archived competitor cannot be used")
        return entity

    def _require_product(self, entity_id: uuid.UUID) -> Product:
        entity = self.repository.get_product(entity_id)
        if entity is None:
            raise UniverseNotFoundError("product not found")
        return entity

    def _require_active_product(self, entity_id: uuid.UUID) -> Product:
        entity = self._require_product(entity_id)
        if entity.archived_at is not None:
            raise UniverseValidationError("archived product cannot be used")
        return entity

    def _require_competitor_product(self, entity_id: uuid.UUID) -> CompetitorProduct:
        entity = self.repository.get_competitor_product(entity_id)
        if entity is None:
            raise UniverseNotFoundError("competitor product not found")
        return entity

    def _require_active_competitor_product(self, entity_id: uuid.UUID) -> CompetitorProduct:
        entity = self._require_competitor_product(entity_id)
        if entity.archived_at is not None:
            raise UniverseValidationError("archived competitor product cannot be used")
        return entity

    def _require_battle_card(self, entity_id: uuid.UUID) -> BattleCard:
        entity = self.repository.get_battle_card(entity_id)
        if entity is None:
            raise UniverseNotFoundError("battle card not found")
        return entity

    def _require_active_battle_card(self, entity_id: uuid.UUID) -> BattleCard:
        entity = self._require_battle_card(entity_id)
        if entity.archived_at is not None:
            raise UniverseValidationError(
                "archived battle card cannot be used", code="archived_battle_card"
            )
        return entity

    def _require_battle_card_item(self, entity_id: uuid.UUID) -> BattleCardItem:
        entity = self.repository.get_battle_card_item(entity_id)
        if entity is None:
            raise UniverseNotFoundError(
                "battle card item not found", code="battle_card_item_not_found"
            )
        return entity

    def _ensure_competitor_name_available(
        self, name: str, *, exclude_id: uuid.UUID | None = None
    ) -> None:
        if self.repository.active_competitor_name_exists(name, exclude_id=exclude_id):
            raise UniverseConflictError(
                "An active competitor with this name already exists", code="competitor_conflict"
            )

    def _ensure_product_available(
        self,
        sku: str,
        marketplace: Marketplace,
        identity: str | None,
        *,
        exclude_id: uuid.UUID | None = None,
    ) -> None:
        if self.repository.active_product_sku_exists(sku, exclude_id=exclude_id):
            raise UniverseConflictError(
                "An active product with this internal SKU already exists",
                code="product_sku_conflict",
            )
        if self.repository.active_product_identity_exists(
            marketplace, identity, exclude_id=exclude_id
        ):
            raise UniverseConflictError(
                "This active marketplace product is already tracked",
                code="product_identity_conflict",
            )

    def _ensure_competitor_product_identity_available(
        self,
        marketplace: Marketplace,
        identity: str | None,
        *,
        exclude_id: uuid.UUID | None = None,
    ) -> None:
        if self.repository.active_competitor_product_identity_exists(
            marketplace, identity, exclude_id=exclude_id
        ):
            raise UniverseConflictError(
                "This active marketplace product is already tracked by a competitor product",
                code="competitor_product_conflict",
            )

    def _ensure_item_mapping_available(
        self,
        battle_card_id: uuid.UUID,
        competitor_product_id: uuid.UUID,
        *,
        exclude_id: uuid.UUID | None = None,
    ) -> None:
        if self.repository.active_battle_card_item_exists(
            battle_card_id, competitor_product_id, exclude_id=exclude_id
        ):
            raise UniverseConflictError(
                "The competitor product is already active in this battle card",
                code="battle_card_item_conflict",
            )

    def _persist[EntityT](self, entity: EntityT) -> EntityT:
        self.repository.add(entity)
        self._commit()
        return entity

    def _set_archive[EntityT: Archivable](self, entity: EntityT, *, archived: bool) -> EntityT:
        entity.archived_at = datetime.now(UTC) if archived else None
        return self._persist(entity)

    def _commit(self) -> None:
        try:
            self.repository.commit()
        except IntegrityError as error:
            self.repository.rollback()
            raise UniverseConflictError(self._integrity_message(error)) from error

    @staticmethod
    def _apply(entity: Any, values: dict[str, Any]) -> None:
        for field, value in values.items():
            setattr(entity, field, value)

    @staticmethod
    def _integrity_message(error: IntegrityError) -> str:
        constraint = getattr(getattr(error.orig, "diag", None), "constraint_name", None)
        messages = {
            "uq_competitors_normalized_active_name": "an active competitor with this name exists",
            "uq_products_active_internal_sku": "a product with this internal SKU exists",
            "uq_products_active_marketplace_identity": (
                "this marketplace product is already tracked"
            ),
            "uq_competitor_products_active_marketplace_identity": (
                "this marketplace product is already tracked by an active competitor product"
            ),
            "uq_battle_card_items_active_mapping": (
                "the competitor product is already in this battle card"
            ),
        }
        if not isinstance(constraint, str):
            return "the record conflicts with existing universe data"
        return messages.get(constraint, "the record conflicts with existing universe data")
