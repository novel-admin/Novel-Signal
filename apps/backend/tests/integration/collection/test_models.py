from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from novel_signal.db import Base
from novel_signal.modules.collection.models import (
    CollectionAttempt,
    CollectionAttemptStatus,
    CollectionFailure,
    CollectionFailureType,
    CollectionJob,
    CollectionJobStatus,
    CollectionJobType,
    CollectionSourceTier,
    DataQualityCheck,
    DataQualityCheckType,
    DataQualityStatus,
    ParserVersion,
    QuarantineRecord,
    RawEvidence,
)
from novel_signal.modules.keywords.models import (
    IntentCluster,
    Keyword,
    KeywordTrackingStatus,
)
from novel_signal.modules.universe.models import Marketplace, Product, TrackingTier  # noqa: F401
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
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(database)
    yield database
    Base.metadata.drop_all(database)
    database.dispose()


def make_keyword() -> Keyword:
    return Keyword(
        keyword_text="baby diapers",
        normalized_text="baby diapers",
        marketplace=Marketplace.AMAZON_IN,
        category="Baby Care",
        tier=TrackingTier.T1,
        tracking_status=KeywordTrackingStatus.ACTIVE,
        intent_cluster=IntentCluster.GENERIC_CATEGORY,
    )


def make_job(
    keyword: Keyword, *, key: str = "amazon_in:serp:kw:2026-08-16T04:00:00Z"
) -> CollectionJob:
    return CollectionJob(
        idempotency_key=key,
        job_type=CollectionJobType.SERP,
        source_tier=CollectionSourceTier.PUBLIC_PAGE,
        platform="amazon_in",
        keyword_id=keyword.id,
        scheduled_for=datetime(2026, 8, 16, 4, 0, tzinfo=UTC),
    )


def test_collection_job_defaults_and_idempotency(engine: Engine) -> None:
    with Session(engine) as session:
        keyword = make_keyword()
        session.add(keyword)
        session.flush()
        first = make_job(keyword)
        session.add(first)
        session.commit()

        assert first.status is CollectionJobStatus.PENDING
        assert first.attempt_count == 0
        assert first.max_attempts == 3

        session.add(make_job(keyword))
        with pytest.raises(IntegrityError):
            session.commit()


def test_collection_job_requires_subject(engine: Engine) -> None:
    with Session(engine) as session:
        session.add(
            CollectionJob(
                idempotency_key="subjectless",
                job_type=CollectionJobType.SERP,
                source_tier=CollectionSourceTier.PUBLIC_PAGE,
                platform="amazon_in",
                scheduled_for=datetime(2026, 8, 16, 4, 0, tzinfo=UTC),
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_attempt_number_is_unique_per_job(engine: Engine) -> None:
    with Session(engine) as session:
        keyword = make_keyword()
        session.add(keyword)
        session.flush()
        job = make_job(keyword)
        session.add(job)
        session.flush()
        session.add_all(
            [
                CollectionAttempt(
                    job_id=job.id,
                    attempt_number=1,
                    status=CollectionAttemptStatus.FAILED,
                ),
                CollectionAttempt(
                    job_id=job.id,
                    attempt_number=1,
                    status=CollectionAttemptStatus.RUNNING,
                ),
            ]
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_failure_and_raw_evidence_keep_audit_links(engine: Engine) -> None:
    with Session(engine) as session:
        keyword = make_keyword()
        session.add(keyword)
        session.flush()
        job = make_job(keyword)
        attempt = CollectionAttempt(
            job=job,
            attempt_number=1,
            status=CollectionAttemptStatus.FAILED,
            retryable=True,
        )
        failure = CollectionFailure(
            job=job,
            attempt=attempt,
            failure_type=CollectionFailureType.CHALLENGE,
            message="Marketplace challenge detected; capture backed off",
            retryable=True,
        )
        evidence = RawEvidence(
            job=job,
            attempt=attempt,
            sha256="a" * 64,
            storage_bucket="novel-signal-raw",
            object_key="sha256/aa/" + "a" * 64,
            content_type="text/html",
            byte_length=128,
            challenge_detected=True,
        )
        session.add_all([failure, evidence])
        session.commit()

        assert job.failures == [failure]
        assert job.raw_evidence == [evidence]
        assert evidence.challenge_detected is True
        assert not hasattr(evidence, "updated_at")


def test_parser_version_identity_and_quarantine(engine: Engine) -> None:
    with Session(engine) as session:
        parser = ParserVersion(platform="amazon_in", page_type="serp", version="1.0.0")
        keyword = make_keyword()
        session.add(keyword)
        session.flush()
        job = make_job(keyword)
        evidence = RawEvidence(
            job=job,
            sha256="b" * 64,
            storage_bucket="novel-signal-raw",
            object_key="sha256/bb/" + "b" * 64,
            content_type="text/html",
            byte_length=64,
        )
        quarantine = QuarantineRecord(
            job=job,
            raw_evidence=evidence,
            parser_version=parser,
            reason_code="schema_validation_failed",
            reason="Required SERP fields were missing",
            schema_errors=[{"field": "results", "message": "required"}],
        )
        session.add(quarantine)
        session.commit()

        assert quarantine.raw_evidence is evidence
        assert quarantine.parser_version is parser
        assert job.quarantine_records == [quarantine]

        session.add(ParserVersion(platform="amazon_in", page_type="serp", version="1.0.0"))
        with pytest.raises(IntegrityError):
            session.commit()


def test_data_quality_check_persists_status(engine: Engine) -> None:
    with Session(engine) as session:
        check = DataQualityCheck(
            check_type=DataQualityCheckType.COMPLETENESS,
            status=DataQualityStatus.WARN,
            scope_type="platform",
            scope_key="amazon_in",
            observed_value={"success_rate": 0.97},
            expected_value={"minimum": 0.98},
            sample_size=100,
        )
        session.add(check)
        session.commit()

        assert check.check_type is DataQualityCheckType.COMPLETENESS
        assert check.status is DataQualityStatus.WARN
