from __future__ import annotations

import importlib
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from novel_signal.db import Base
from novel_signal.modules.collection.amazon_product_executor import AmazonProductExecutor
from novel_signal.modules.collection.amazon_serp_executor import AmazonSerpExecutor
from novel_signal.modules.collection.execution import get_executor
from novel_signal.modules.collection.models import (
    CollectionJob,
    CollectionJobStatus,
    CollectionJobType,
    CollectionSourceTier,
)
from novel_signal.modules.collection.repository import CollectionRepository
from novel_signal.modules.collection.service import (
    CollectionLifecycleService,
    CollectionPlanningService,
)
from novel_signal.modules.keywords.models import (
    IntentCluster,
    Keyword,
    KeywordTrackingStatus,
    TrackingTarget,
)
from novel_signal.modules.universe.models import (
    Competitor,
    CompetitorProduct,
    Marketplace,
    Product,
    TrackingTier,
)
from novel_signal.tasks import collection as collection_tasks
from sqlalchemy import Engine, create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

NOW = datetime(2026, 8, 31, 8, 15, tzinfo=UTC)


@pytest.fixture
def engine() -> Iterator[Engine]:
    database = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(database, "connect")
    def foreign_keys(connection: object, _: object) -> None:
        cursor = connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(database)
    yield database
    Base.metadata.drop_all(database)
    database.dispose()


def _seed(session: Session) -> tuple[Keyword, Product, CompetitorProduct]:
    keyword = Keyword(
        keyword_text="baby wipes",
        normalized_text="baby wipes",
        marketplace=Marketplace.AMAZON_IN,
        tier=TrackingTier.T1,
        tracking_status=KeywordTrackingStatus.ACTIVE,
        intent_cluster=IntentCluster.GENERIC_CATEGORY,
    )
    product = Product(
        internal_sku="OWN-WIPES-1",
        name="Novel Wipes",
        brand="Novel",
        category="Baby Care",
        marketplace=Marketplace.AMAZON_IN,
        marketplace_product_id="B0TEST0001",
        tracking_tier=TrackingTier.T1,
    )
    competitor = Competitor(name="Acme")
    competitor_product = CompetitorProduct(
        competitor=competitor,
        name="Acme Wipes",
        brand="Acme",
        category="Baby Care",
        marketplace=Marketplace.AMAZON_IN,
        marketplace_product_id="B0TEST0002",
        tracking_tier=TrackingTier.T1,
    )
    session.add_all([keyword, product, competitor_product])
    session.flush()
    session.add_all(
        [
            TrackingTarget(keyword=keyword, product=product, cadence_minutes=60, enabled=True),
            TrackingTarget(
                keyword=keyword,
                competitor_product=competitor_product,
                cadence_minutes=60,
                enabled=True,
            ),
        ]
    )
    session.flush()
    return keyword, product, competitor_product


def test_week2_planning_dispatch_registry_and_lifecycle_acceptance(engine: Engine) -> None:
    importlib.reload(collection_tasks)  # Worker-module load performs normal registration.
    assert isinstance(get_executor("amazon_in", CollectionJobType.SERP), AmazonSerpExecutor)
    assert isinstance(
        get_executor("amazon_in", CollectionJobType.PRODUCT_DETAIL), AmazonProductExecutor
    )

    with Session(engine, expire_on_commit=False) as session:
        keyword, product, competitor_product = _seed(session)
        planner = CollectionPlanningService(session)
        first = planner.plan_due(at=NOW)
        session.commit()

        assert first.created == 3
        assert first.existing == 0
        jobs = {
            job.job_type.value
            + ":"
            + str(job.keyword_id or job.product_id or job.competitor_product_id): job
            for job in first.jobs
        }
        serp = jobs[f"serp:{keyword.id}"]
        owned = jobs[f"product_detail:{product.id}"]
        competitor = jobs[f"product_detail:{competitor_product.id}"]
        assert serp.platform == "amazon_in"
        assert serp.source_tier is CollectionSourceTier.PUBLIC_PAGE
        assert serp.scheduled_for == serp.not_before == datetime(2026, 8, 31, 8, tzinfo=UTC)
        assert owned.product_id == product.id and owned.competitor_product_id is None
        assert (
            competitor.competitor_product_id == competitor_product.id
            and competitor.product_id is None
        )

        replay = planner.plan_due(at=NOW)
        session.commit()
        assert replay.created == 0
        assert replay.existing == 3
        assert len(session.scalars(select(CollectionJob)).all()) == 3

        pending = CollectionRepository(session).pending_dispatch_jobs(now=NOW)
        assert {job.id for job in pending} == {serp.id, owned.id, competitor.id}

        lifecycle = CollectionLifecycleService(session)
        for job in (serp, owned, competitor):
            claim = lifecycle.claim_attempt(job.id, at=NOW)
            assert claim is not None
            assert claim.job.status is CollectionJobStatus.RUNNING
            assert claim.job.attempt_count == 1
            assert claim.item.job_id == job.id
            assert claim.item.attempt_id == claim.attempt.id
            if job.job_type is CollectionJobType.SERP:
                assert claim.item.keyword_id == keyword.id
                assert claim.item.product_id is None
                assert claim.item.competitor_product_id is None
            elif job.product_id is not None:
                assert claim.item.product_id == product.id
                assert claim.item.competitor_product_id is None
            else:
                assert claim.item.competitor_product_id == competitor_product.id
                assert claim.item.product_id is None
        session.commit()
