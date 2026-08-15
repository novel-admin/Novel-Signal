from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from novel_signal.config import get_settings
from novel_signal.modules.universe.models import (
    Competitor,
    CompetitorProduct,
    Marketplace,
    PositioningTier,
    TrackingTier,
)
from sqlalchemy import Engine, create_engine, delete, inspect
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session


@pytest.fixture
def postgres_engine() -> Iterator[Engine]:
    database = create_engine(get_settings().database_url, pool_pre_ping=True)
    if database.dialect.name != "postgresql":
        database.dispose()
        pytest.skip("PostgreSQL integration test requires a PostgreSQL database")
    try:
        with database.connect() as connection:
            if not inspect(connection).has_table("competitors"):
                pytest.skip("S1 migration has not been applied to the PostgreSQL database")
    except OperationalError:
        database.dispose()
        pytest.skip("PostgreSQL test database is not available")

    yield database
    database.dispose()


@pytest.fixture
def postgres_session(postgres_engine: Engine) -> Iterator[Session]:
    connection = postgres_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


def test_postgres_active_name_index_archive_reuse_and_enum_persistence(
    postgres_session: Session,
) -> None:
    name = f"Acme-{uuid4()}"
    competitor = Competitor(
        name=name,
        positioning_tier=PositioningTier.PREMIUM,
        amazon_store_url="https://www.amazon.in/stores/example",
        amazon_seller_id="SELLER-001",
        category_presence="Baby Care",
    )
    postgres_session.add(competitor)
    postgres_session.flush()

    with pytest.raises(IntegrityError), postgres_session.begin_nested():
        postgres_session.add(Competitor(name=f"  {name.lower()}  "))
        postgres_session.flush()

    competitor.archived_at = datetime.now(UTC)
    postgres_session.flush()
    replacement = Competitor(name=f"  {name.lower()}  ")
    postgres_session.add(replacement)
    postgres_session.flush()
    postgres_session.expire_all()

    persisted = postgres_session.get(Competitor, competitor.id)
    assert persisted is not None
    assert persisted.positioning_tier is PositioningTier.PREMIUM
    assert replacement.id is not None


def test_postgres_competitor_product_uniqueness_and_fk_restriction(
    postgres_session: Session,
) -> None:
    competitor = Competitor(name=f"Competitor-{uuid4()}")
    other_competitor = Competitor(name=f"Other-{uuid4()}")
    marketplace_product_id = f"ID-{uuid4()}"
    competitor_product = CompetitorProduct(
        competitor=competitor,
        name="Tracked product",
        brand="Tracked brand",
        category="Baby Care",
        marketplace=Marketplace.AMAZON_IN,
        marketplace_product_id=marketplace_product_id,
        tracking_tier=TrackingTier.T2,
    )
    postgres_session.add_all([competitor_product, other_competitor])
    postgres_session.flush()

    with pytest.raises(IntegrityError), postgres_session.begin_nested():
        postgres_session.add(
            CompetitorProduct(
                competitor=other_competitor,
                name="Duplicate tracked product",
                brand="Tracked brand",
                category="Baby Care",
                marketplace=Marketplace.AMAZON_IN,
                marketplace_product_id=marketplace_product_id,
                tracking_tier=TrackingTier.T3,
            )
        )
        postgres_session.flush()

    with pytest.raises(IntegrityError), postgres_session.begin_nested():
        postgres_session.execute(delete(Competitor).where(Competitor.id == competitor.id))
        postgres_session.flush()
