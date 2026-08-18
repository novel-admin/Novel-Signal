from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient
from novel_signal.db import Base, get_db
from novel_signal.main import app
from novel_signal.modules.keywords.models import IntentCluster, Keyword, KeywordTrackingStatus
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
class S3Context:
    client: TestClient
    session: Session
    keyword: Keyword
    product: Product
    competitor_product: CompetitorProduct


@pytest.fixture
def s3() -> Iterator[S3Context]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection: object, _: object) -> None:
        cursor = connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        keyword = Keyword(
            keyword_text="baby wipes",
            normalized_text="baby wipes",
            marketplace=Marketplace.AMAZON_IN,
            tier=TrackingTier.T1,
            tracking_status=KeywordTrackingStatus.ACTIVE,
            intent_cluster=IntentCluster.GENERIC_CATEGORY,
        )
        product = Product(
            internal_sku="OWN-1",
            name="Owned wipes",
            brand="Novel",
            category="Wipes",
            marketplace=Marketplace.AMAZON_IN,
            marketplace_product_id="OWN1",
            tracking_tier=TrackingTier.T1,
        )
        competitor = Competitor(
            name="Acme",
            positioning_tier=PositioningTier.MID,
        )
        competitor_product = CompetitorProduct(
            competitor=competitor,
            name="Acme wipes",
            brand="Acme",
            category="Wipes",
            marketplace=Marketplace.AMAZON_IN,
            marketplace_product_id="COMP1",
            tracking_tier=TrackingTier.T1,
        )
        session.add_all([keyword, product, competitor_product])
        session.commit()

        def override() -> Iterator[Session]:
            yield session

        app.dependency_overrides[get_db] = override
        with TestClient(app) as client:
            yield S3Context(client, session, keyword, product, competitor_product)
        app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()
