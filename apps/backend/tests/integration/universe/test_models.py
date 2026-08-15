from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from novel_signal.db import Base
from novel_signal.modules.universe.models import (
    BattleCard,
    BattleCardItem,
    Competitor,
    CompetitorProduct,
    Marketplace,
    PositioningTier,
    Product,
    TrackingTier,
)
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool


@pytest.fixture
def engine() -> Iterator[Engine]:
    database = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(database, "connect")
    def enable_foreign_keys(dbapi_connection: object, _connection_record: object) -> None:
        dbapi_connection.create_function(  # type: ignore[attr-defined]
            "btrim", 1, lambda value: value.strip(), deterministic=True
        )
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(database)
    yield database
    Base.metadata.drop_all(database)
    database.dispose()


def make_product(*, internal_sku: str = "OWN-001", marketplace_id: str = "B000000001") -> Product:
    return Product(
        internal_sku=internal_sku,
        name="Owned Product",
        brand="Owned Brand",
        category="Baby Care",
        marketplace=Marketplace.AMAZON_IN,
        marketplace_product_id=marketplace_id,
        pack_quantity=10,
        pack_unit="pieces",
        tracking_tier=TrackingTier.T1,
    )


def make_competitor_product(
    competitor: Competitor, *, marketplace_id: str = "B000000002"
) -> CompetitorProduct:
    return CompetitorProduct(
        competitor=competitor,
        name="Competitor Product",
        brand=competitor.name,
        category="Baby Care",
        marketplace=Marketplace.AMAZON_IN,
        marketplace_product_id=marketplace_id,
        pack_quantity=12,
        pack_unit="pieces",
        tracking_tier=TrackingTier.T1,
    )


def test_required_relationships_persist(engine: Engine) -> None:
    with Session(engine) as session:
        competitor = Competitor(name="Acme", positioning_tier=PositioningTier.MID, threat_rating=4)
        product = make_product()
        competitor_product = make_competitor_product(competitor)
        battle_card = BattleCard(product=product, name="Primary comparison")
        item = BattleCardItem(
            battle_card=battle_card,
            competitor_product=competitor_product,
            priority_order=1,
            same_pack_basis=True,
            same_category=True,
        )
        session.add(item)
        session.commit()

        assert competitor.competitor_products == [competitor_product]
        assert product.battle_cards == [battle_card]
        assert battle_card.items == [item]
        assert item.competitor_product is competitor_product
        assert all(record.id is not None for record in (competitor, product, item))


def test_active_competitor_name_is_normalized_and_unique(engine: Engine) -> None:
    with Session(engine) as session:
        session.add(Competitor(name="  Acme  "))
        session.commit()

        session.add(Competitor(name="acme"))
        with pytest.raises(IntegrityError):
            session.commit()


def test_archived_competitor_name_can_be_reused(engine: Engine) -> None:
    with Session(engine) as session:
        competitor = Competitor(name="Acme")
        session.add(competitor)
        session.commit()

        competitor.archived_at = datetime.now(UTC)
        session.commit()

        session.add(Competitor(name="  acme  "))
        session.commit()


def test_updated_at_changes_on_orm_update(engine: Engine) -> None:
    with Session(engine) as session:
        competitor = Competitor(name="Acme")
        session.add(competitor)
        session.commit()
        previous_updated_at = competitor.updated_at

        competitor.notes = "Reviewed"
        session.commit()

        assert competitor.updated_at > previous_updated_at


def test_product_internal_sku_and_marketplace_identity_are_unique(engine: Engine) -> None:
    with Session(engine) as session:
        session.add(make_product())
        session.commit()

        session.add(make_product(internal_sku="OWN-002"))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        session.add(make_product(internal_sku="OWN-001", marketplace_id="B000000099"))
        with pytest.raises(IntegrityError):
            session.commit()


def test_competitor_marketplace_identity_is_unique_across_competitors(engine: Engine) -> None:
    with Session(engine) as session:
        first_competitor = Competitor(name="First")
        second_competitor = Competitor(name="Second")
        session.add(make_competitor_product(first_competitor))
        session.commit()

        session.add(make_competitor_product(second_competitor))
        with pytest.raises(IntegrityError):
            session.commit()


def test_battle_card_cannot_repeat_competitor_product(engine: Engine) -> None:
    with Session(engine) as session:
        competitor = Competitor(name="Acme")
        competitor_product = make_competitor_product(competitor)
        battle_card = BattleCard(product=make_product(), name="Primary comparison")
        session.add_all(
            [
                BattleCardItem(battle_card=battle_card, competitor_product=competitor_product),
                BattleCardItem(battle_card=battle_card, competitor_product=competitor_product),
            ]
        )
        with pytest.raises(IntegrityError):
            session.commit()


@pytest.mark.parametrize("pack_quantity", [0, -1])
def test_pack_quantity_must_be_positive(engine: Engine, pack_quantity: int) -> None:
    with Session(engine) as session:
        product = make_product()
        product.pack_quantity = pack_quantity
        session.add(product)
        with pytest.raises(IntegrityError):
            session.commit()


@pytest.mark.parametrize("threat_rating", [0, 6])
def test_threat_rating_must_be_between_one_and_five(engine: Engine, threat_rating: int) -> None:
    with Session(engine) as session:
        session.add(Competitor(name="Acme", threat_rating=threat_rating))
        with pytest.raises(IntegrityError):
            session.commit()
