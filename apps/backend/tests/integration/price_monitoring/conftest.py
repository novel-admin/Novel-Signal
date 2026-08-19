from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient
from novel_signal.db import Base, get_db
from novel_signal.main import app
from novel_signal.modules.universe.models import (
    Competitor,
    CompetitorProduct,
    Marketplace,
    PositioningTier,
    Product,
    TrackingTier,
)
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool


@dataclass
class Context:
    client: TestClient
    session: Session
    product: Product
    competitor_product: CompetitorProduct


@pytest.fixture
def s6() -> Iterator[Context]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def configure(connection: object, _: object) -> None:
        connection.create_function("btrim", 1, lambda value: value.strip(), deterministic=True)  # type: ignore[attr-defined]
        cursor = connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        product = Product(
            internal_sku="S6-OWN",
            name="Owned",
            brand="Novel",
            category="Care",
            marketplace=Marketplace.AMAZON_IN,
            marketplace_product_id="OWN-S6",
            tracking_tier=TrackingTier.T1,
        )
        competitor = Competitor(name="S6 Competitor", positioning_tier=PositioningTier.MID)
        competitor_product = CompetitorProduct(
            competitor=competitor,
            name="Competitor product",
            brand="Acme",
            category="Care",
            marketplace=Marketplace.AMAZON_IN,
            marketplace_product_id="COMP-S6",
            tracking_tier=TrackingTier.T1,
        )
        session.add_all([product, competitor_product])
        session.commit()

        def override() -> Iterator[Session]:
            yield session

        app.dependency_overrides[get_db] = override
        with TestClient(app) as client:
            yield Context(client, session, product, competitor_product)
        app.dependency_overrides.clear()
    engine.dispose()
