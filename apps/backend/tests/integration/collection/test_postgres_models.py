from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from novel_signal.config import get_settings
from novel_signal.modules.collection.models import (
    CollectionAttempt,
    CollectionAttemptStatus,
    CollectionJob,
    CollectionJobStatus,
    CollectionJobType,
    CollectionSourceTier,
    RawEvidence,
)
from novel_signal.modules.keywords.models import (
    IntentCluster,
    Keyword,
    KeywordTrackingStatus,
)
from novel_signal.modules.universe.models import Marketplace, TrackingTier
from sqlalchemy import Engine, create_engine, inspect
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
            if not inspect(connection).has_table("collection_jobs"):
                pytest.skip("S12 Phase 1 migration has not been applied to PostgreSQL")
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


def make_keyword() -> Keyword:
    token = uuid4().hex
    return Keyword(
        keyword_text=f"s12 keyword {token}",
        normalized_text=f"s12 keyword {token}",
        marketplace=Marketplace.AMAZON_IN,
        category="Baby Care",
        tier=TrackingTier.T1,
        tracking_status=KeywordTrackingStatus.ACTIVE,
        intent_cluster=IntentCluster.GENERIC_CATEGORY,
    )


def test_postgres_job_idempotency_and_enum_round_trip(postgres_session: Session) -> None:
    keyword = make_keyword()
    postgres_session.add(keyword)
    postgres_session.flush()
    idempotency_key = f"amazon_in:serp:{keyword.id}:2026-08-16T04:00:00Z"
    job = CollectionJob(
        idempotency_key=idempotency_key,
        job_type=CollectionJobType.SERP,
        source_tier=CollectionSourceTier.PUBLIC_PAGE,
        platform="amazon_in",
        keyword_id=keyword.id,
        scheduled_for=datetime(2026, 8, 16, 4, 0, tzinfo=UTC),
    )
    postgres_session.add(job)
    postgres_session.flush()

    with pytest.raises(IntegrityError), postgres_session.begin_nested():
        postgres_session.add(
            CollectionJob(
                idempotency_key=idempotency_key,
                job_type=CollectionJobType.SERP,
                source_tier=CollectionSourceTier.PUBLIC_PAGE,
                platform="amazon_in",
                keyword_id=keyword.id,
                scheduled_for=datetime(2026, 8, 16, 4, 0, tzinfo=UTC),
            )
        )
        postgres_session.flush()

    postgres_session.expire(job)
    assert job.status is CollectionJobStatus.PENDING
    assert job.job_type is CollectionJobType.SERP
    assert job.source_tier is CollectionSourceTier.PUBLIC_PAGE


def test_postgres_attempt_and_raw_evidence_relationships(postgres_session: Session) -> None:
    keyword = make_keyword()
    postgres_session.add(keyword)
    postgres_session.flush()
    job = CollectionJob(
        idempotency_key=f"amazon_in:serp:{keyword.id}:relationship-test",
        job_type=CollectionJobType.SERP,
        source_tier=CollectionSourceTier.PUBLIC_PAGE,
        platform="amazon_in",
        keyword_id=keyword.id,
        scheduled_for=datetime.now(UTC),
    )
    attempt = CollectionAttempt(
        job=job,
        attempt_number=1,
        status=CollectionAttemptStatus.SUCCEEDED,
    )
    evidence = RawEvidence(
        job=job,
        attempt=attempt,
        sha256="c" * 64,
        storage_bucket="novel-signal-raw",
        object_key=f"sha256/cc/{'c' * 64}",
        content_type="text/html",
        byte_length=256,
    )
    postgres_session.add(evidence)
    postgres_session.flush()

    assert attempt in job.attempts
    assert evidence in job.raw_evidence
    assert evidence.attempt is attempt
