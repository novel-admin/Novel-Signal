from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from novel_signal.db import Base
from novel_signal.modules.collection import runner
from novel_signal.modules.collection.execution import (
    CollectionExecutionError,
    CollectionExecutionResult,
    CollectionWorkItem,
    QuarantineDecision,
    clear_executor_registry,
    register_executor,
)
from novel_signal.modules.collection.models import (
    CollectionFailureType,
    CollectionJob,
    CollectionJobStatus,
    CollectionJobType,
    CollectionSourceTier,
    ParserVersion,
    RawEvidence,
    RawEvidenceType,
)
from novel_signal.modules.keywords.models import (
    IntentCluster,
    Keyword,
    KeywordTrackingStatus,
)
from novel_signal.modules.universe.models import Marketplace, TrackingTier
from sqlalchemy import Engine, create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
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
    clear_executor_registry()


def seed_job(session: Session, *, max_attempts: int = 1) -> CollectionJob:
    keyword = Keyword(
        keyword_text="baby diapers",
        normalized_text="baby diapers",
        marketplace=Marketplace.AMAZON_IN,
        category="Baby Care",
        tier=TrackingTier.T1,
        tracking_status=KeywordTrackingStatus.ACTIVE,
        intent_cluster=IntentCluster.GENERIC_CATEGORY,
    )
    session.add(keyword)
    session.flush()
    job = CollectionJob(
        idempotency_key=f"task-test-{max_attempts}",
        job_type=CollectionJobType.SERP,
        source_tier=CollectionSourceTier.PUBLIC_PAGE,
        platform="amazon_in",
        keyword_id=keyword.id,
        scheduled_for=datetime(2026, 8, 17, 4, 0, tzinfo=UTC),
        max_attempts=max_attempts,
    )
    session.add(job)
    session.commit()
    return job


class SuccessfulExecutor:
    async def execute(self, item: CollectionWorkItem) -> CollectionExecutionResult:
        return CollectionExecutionResult(metadata={"executor": "fake", "job": str(item.job_id)})


class ChallengeExecutor:
    async def execute(self, item: CollectionWorkItem) -> CollectionExecutionResult:
        raise CollectionExecutionError(
            f"Challenge detected for {item.job_id}",
            failure_type=CollectionFailureType.CHALLENGE,
            code="marketplace_challenge",
            retryable=True,
            details={"backed_off": True},
        )


class QuarantineExecutor:
    def __init__(self, raw_id: object, parser_id: object) -> None:
        self.raw_id = raw_id
        self.parser_id = parser_id

    async def execute(self, item: CollectionWorkItem) -> CollectionExecutionResult:
        return CollectionExecutionResult(
            quarantine=QuarantineDecision(
                raw_evidence_id=self.raw_id,  # type: ignore[arg-type]
                parser_version_id=self.parser_id,  # type: ignore[arg-type]
                failure_type=CollectionFailureType.VALIDATION_ERROR,
                reason_code="schema_validation_failed",
                reason="Seeded validation failure",
                schema_errors=({"code": "required_field_missing"},),
                parsed_payload=[{"position": 1}],
            )
        )


def test_scheduled_execution_marks_job_succeeded(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(runner, "SessionLocal", factory)
    register_executor("amazon_in", CollectionJobType.SERP, SuccessfulExecutor)

    with factory() as session:
        job = seed_job(session)
        job_id = job.id

    result = runner.run_collection_job(job_id)
    assert result["status"] == "succeeded"

    with factory() as session:
        stored = session.get(CollectionJob, job_id)
        assert stored is not None
        assert stored.status is CollectionJobStatus.SUCCEEDED
        assert stored.attempt_count == 1
        assert stored.attempts[0].attempt_metadata is not None
        assert stored.attempts[0].attempt_metadata["executor"] == "fake"


def test_challenge_is_recorded_and_not_bypassed(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(runner, "SessionLocal", factory)
    register_executor("amazon_in", CollectionJobType.SERP, ChallengeExecutor)

    with factory() as session:
        job = seed_job(session, max_attempts=1)
        job_id = job.id

    result = runner.run_collection_job(job_id)
    assert result["status"] == "failed"
    assert result["error_code"] == "marketplace_challenge"

    with factory() as session:
        stored = session.scalar(select(CollectionJob).where(CollectionJob.id == job_id))
        assert stored is not None
        assert stored.status is CollectionJobStatus.FAILED
        assert stored.attempt_count == 1
        assert len(stored.failures) == 1
        assert stored.failures[0].failure_type is CollectionFailureType.CHALLENGE
        assert stored.failures[0].details == {"backed_off": True}


def test_quarantine_result_marks_job_and_attempt_quarantined(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(runner, "SessionLocal", factory)

    with factory() as session:
        job = seed_job(session)
        job_id = job.id
        parser = ParserVersion(platform="amazon_in", page_type="serp", version="v1")
        session.add(parser)
        session.flush()
        raw = RawEvidence(
            job_id=job.id,
            evidence_type=RawEvidenceType.RESPONSE_BODY,
            sha256="a" * 64,
            storage_bucket="raw",
            object_key="raw/a.gz",
            content_type="text/html",
            byte_length=10,
        )
        session.add(raw)
        session.commit()
        raw_id = raw.id
        parser_id = parser.id

    register_executor(
        "amazon_in",
        CollectionJobType.SERP,
        lambda: QuarantineExecutor(raw_id, parser_id),
    )
    result = runner.run_collection_job(job_id)
    assert result["status"] == "quarantined"

    with factory() as session:
        stored = session.get(CollectionJob, job_id)
        assert stored is not None
        assert stored.status is CollectionJobStatus.QUARANTINED
        assert stored.attempts[0].status.value == "quarantined"
        assert len(stored.quarantine_records) == 1
        assert stored.quarantine_records[0].raw_evidence_id == raw_id
