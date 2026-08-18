from __future__ import annotations

import random
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from novel_signal.db import Base
from novel_signal.modules.collection.models import (
    CollectionAttemptStatus,
    CollectionFailureType,
    CollectionJob,
    CollectionJobStatus,
    CollectionJobType,
    CollectionSourceTier,
)
from novel_signal.modules.collection.service import (
    CollectionLifecycleService,
    CollectionPlanningService,
    cadence_slot,
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
from sqlalchemy import Engine, create_engine, event, select
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
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(database)
    yield database
    Base.metadata.drop_all(database)
    database.dispose()


def seed_tracking_configuration(session: Session) -> tuple[Keyword, Product, CompetitorProduct]:
    keyword = Keyword(
        keyword_text="baby diapers",
        normalized_text="baby diapers",
        marketplace=Marketplace.AMAZON_IN,
        category="Baby Care",
        tier=TrackingTier.T1,
        tracking_status=KeywordTrackingStatus.ACTIVE,
        intent_cluster=IntentCluster.GENERIC_CATEGORY,
    )
    product = Product(
        internal_sku="OWN-001",
        name="Owned Product",
        brand="Owned Brand",
        category="Baby Care",
        marketplace=Marketplace.AMAZON_IN,
        marketplace_product_id="B000000001",
        tracking_tier=TrackingTier.T1,
    )
    competitor = Competitor(name="Acme")
    competitor_product = CompetitorProduct(
        competitor=competitor,
        name="Competitor Product",
        brand="Acme",
        category="Baby Care",
        marketplace=Marketplace.AMAZON_IN,
        marketplace_product_id="B000000002",
        tracking_tier=TrackingTier.T1,
    )
    session.add_all([keyword, product, competitor_product])
    session.flush()
    session.add_all(
        [
            TrackingTarget(
                keyword=keyword,
                product=product,
                cadence_minutes=240,
                enabled=True,
            ),
            TrackingTarget(
                keyword=keyword,
                competitor_product=competitor_product,
                cadence_minutes=240,
                enabled=True,
            ),
        ]
    )
    session.flush()
    return keyword, product, competitor_product


def make_job(keyword: Keyword, *, max_attempts: int = 3) -> CollectionJob:
    return CollectionJob(
        idempotency_key=f"manual:{keyword.id}:{max_attempts}",
        job_type=CollectionJobType.SERP,
        source_tier=CollectionSourceTier.PUBLIC_PAGE,
        platform="amazon_in",
        keyword_id=keyword.id,
        scheduled_for=datetime(2026, 8, 17, 4, 0, tzinfo=UTC),
        max_attempts=max_attempts,
    )


def test_cadence_slot_is_stable_and_utc() -> None:
    at = datetime(2026, 8, 17, 6, 37, 55, tzinfo=UTC)
    assert cadence_slot(at, 60) == datetime(2026, 8, 17, 6, 0, tzinfo=UTC)
    assert cadence_slot(at, 240) == datetime(2026, 8, 17, 4, 0, tzinfo=UTC)
    with pytest.raises(ValueError):
        cadence_slot(at, 0)


def test_planner_deduplicates_serp_and_product_jobs(engine: Engine) -> None:
    at = datetime(2026, 8, 17, 6, 37, tzinfo=UTC)
    with Session(engine, expire_on_commit=False) as session:
        seed_tracking_configuration(session)
        first = CollectionPlanningService(session).plan_due(at=at)
        session.commit()

        assert first.created == 3
        assert first.existing == 0
        assert sum(job.job_type is CollectionJobType.SERP for job in first.jobs) == 1
        assert sum(job.job_type is CollectionJobType.PRODUCT_DETAIL for job in first.jobs) == 2

        second = CollectionPlanningService(session).plan_due(at=at)
        session.commit()
        assert second.created == 0
        assert second.existing == 3
        assert session.query(CollectionJob).count() == 3


def test_planner_uses_four_hour_serp_and_hourly_product_slots(engine: Engine) -> None:
    first_at = datetime(2026, 8, 17, 4, 5, tzinfo=UTC)
    second_at = first_at + timedelta(hours=1)
    fourth_hour = first_at + timedelta(hours=4)

    with Session(engine, expire_on_commit=False) as session:
        seed_tracking_configuration(session)
        CollectionPlanningService(session).plan_due(at=first_at)
        session.commit()

        one_hour_later = CollectionPlanningService(session).plan_due(at=second_at)
        session.commit()
        assert one_hour_later.created == 2
        assert one_hour_later.existing == 1

        four_hours_later = CollectionPlanningService(session).plan_due(at=fourth_hour)
        session.commit()
        assert four_hours_later.created == 3
        assert session.query(CollectionJob).count() == 8


def test_disabled_target_does_not_create_serp_job(engine: Engine) -> None:
    with Session(engine) as session:
        keyword, product, _ = seed_tracking_configuration(session)
        for target in keyword.tracking_targets:
            target.enabled = False
        session.flush()

        result = CollectionPlanningService(session).plan_due(
            at=datetime(2026, 8, 17, 4, 5, tzinfo=UTC)
        )
        assert all(job.job_type is CollectionJobType.PRODUCT_DETAIL for job in result.jobs)
        assert product.id is not None


def test_lifecycle_success_is_single_claim(engine: Engine) -> None:
    now = datetime(2026, 8, 17, 4, 0, tzinfo=UTC)
    with Session(engine, expire_on_commit=False) as session:
        keyword, _, _ = seed_tracking_configuration(session)
        job = make_job(keyword)
        session.add(job)
        session.commit()

        lifecycle = CollectionLifecycleService(session)
        claim = lifecycle.claim_attempt(job.id, worker_id="worker-1", at=now)
        assert claim is not None
        assert job.status is CollectionJobStatus.RUNNING
        assert job.attempt_count == 1
        assert lifecycle.claim_attempt(job.id, worker_id="worker-2", at=now) is None

        lifecycle.mark_succeeded(
            job.id,
            claim.attempt.id,
            metadata={"capture": "ok"},
            at=now + timedelta(seconds=2),
        )
        session.commit()
        assert job.status is CollectionJobStatus.SUCCEEDED
        assert claim.attempt.status is CollectionAttemptStatus.SUCCEEDED
        assert claim.attempt.attempt_metadata == {"capture": "ok"}
        assert lifecycle.claim_attempt(job.id, at=now + timedelta(minutes=1)) is None


def test_retryable_failure_sets_backoff_and_preserves_audit(engine: Engine) -> None:
    now = datetime(2026, 8, 17, 4, 0, tzinfo=UTC)
    with Session(engine, expire_on_commit=False) as session:
        keyword, _, _ = seed_tracking_configuration(session)
        job = make_job(keyword)
        session.add(job)
        session.commit()

        lifecycle = CollectionLifecycleService(session, random_source=random.Random(7))
        claim = lifecycle.claim_attempt(job.id, at=now)
        assert claim is not None
        decision = lifecycle.mark_failed(
            job.id,
            claim.attempt.id,
            failure_type=CollectionFailureType.CHALLENGE,
            code="marketplace_challenge",
            message="Marketplace challenge detected; backing off",
            retryable=True,
            details={"challenge": True},
            at=now + timedelta(seconds=1),
        )
        session.commit()

        assert decision.should_retry is True
        assert decision.retry_after_seconds is not None
        assert decision.retry_after_seconds >= 30
        assert job.status is CollectionJobStatus.PENDING
        assert job.not_before is not None
        assert job.failures[0].failure_type is CollectionFailureType.CHALLENGE
        assert job.failures[0].retryable is True
        assert claim.attempt.status is CollectionAttemptStatus.FAILED
        assert lifecycle.claim_attempt(job.id, at=now + timedelta(seconds=2)) is None


def test_final_failure_stops_retrying(engine: Engine) -> None:
    now = datetime(2026, 8, 17, 4, 0, tzinfo=UTC)
    with Session(engine, expire_on_commit=False) as session:
        keyword, _, _ = seed_tracking_configuration(session)
        job = make_job(keyword, max_attempts=1)
        session.add(job)
        session.commit()

        lifecycle = CollectionLifecycleService(session, random_source=random.Random(1))
        claim = lifecycle.claim_attempt(job.id, at=now)
        assert claim is not None
        decision = lifecycle.mark_failed(
            job.id,
            claim.attempt.id,
            failure_type=CollectionFailureType.NETWORK,
            code="network_down",
            message="Temporary network failure",
            retryable=True,
            at=now + timedelta(seconds=1),
        )
        session.commit()

        assert decision.should_retry is False
        assert decision.retry_after_seconds is None
        assert job.status is CollectionJobStatus.FAILED
        assert job.completed_at is not None
        assert lifecycle.claim_attempt(job.id, at=now + timedelta(hours=1)) is None
        stored = session.scalar(select(CollectionJob).where(CollectionJob.id == job.id))
        assert stored is job
