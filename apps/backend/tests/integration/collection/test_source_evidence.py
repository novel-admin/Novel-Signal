from __future__ import annotations

import hashlib
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from novel_signal.db import Base
from novel_signal.modules.collection.execution import CollectionExecutionError
from novel_signal.modules.collection.models import (
    CollectionAttempt,
    CollectionAttemptStatus,
    CollectionFailureType,
    CollectionJob,
    CollectionJobStatus,
    CollectionJobType,
    CollectionSourceTier,
    DataQualityCheck,
    ParserVersion,
    RawEvidence,
)
from novel_signal.modules.collection.source_evidence import SourceRawEvidenceBridge
from novel_signal.modules.collection.storage import StoredRawObject
from novel_signal.modules.keywords.models import IntentCluster, Keyword, KeywordTrackingStatus
from novel_signal.modules.universe.models import Marketplace, TrackingTier
from novel_signal.sources.base import RawSourcePage, SourceType, SyncRequest
from sqlalchemy import Engine, create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

CAPTURED_AT = datetime(2026, 8, 25, 8, 0, tzinfo=UTC)
SYNC_REQUEST = SyncRequest(
    resource_type="catalog_items",
    window_start=datetime(2026, 8, 24, tzinfo=UTC),
    window_end=datetime(2026, 8, 25, tzinfo=UTC),
    cursor={"asin": "B000TEST01"},
)


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


class MemoryStore:
    def __init__(self, *, fail_at: int | None = None) -> None:
        self.calls: list[tuple[str, str, bytes]] = []
        self.fail_at = fail_at

    def put_raw(self, *, platform: str, page_type: str, body: bytes) -> StoredRawObject:
        call_index = len(self.calls)
        self.calls.append((platform, page_type, body))
        if self.fail_at == call_index:
            raise OSError("fake storage failure with token=must-not-leak")
        digest = hashlib.sha256(body).hexdigest()
        return StoredRawObject(
            sha256=digest,
            bucket="test-raw",
            object_key=f"raw/{platform}/{page_type}/{digest}.gz",
            byte_length=len(body),
            compressed_byte_length=max(1, len(body) // 2),
        )


class FakeSourceError(RuntimeError):
    pass


@dataclass
class FakeAdapter:
    pages: tuple[RawSourcePage, ...] = ()
    error: Exception | None = None
    source_type: SourceType = SourceType.AMAZON_SP_API

    async def verify_connection(self) -> None:
        return None

    async def fetch(self, request: SyncRequest) -> tuple[RawSourcePage, ...]:
        if self.error is not None:
            raise self.error
        return self.pages


def raw_page(
    body: bytes,
    *,
    fingerprint: str,
    next_cursor: dict[str, str] | None = None,
) -> RawSourcePage:
    return RawSourcePage(
        source=SourceType.AMAZON_SP_API,
        resource_type="catalog_items",
        body=body,
        content_type="application/json",
        request_fingerprint=fingerprint,
        next_cursor=next_cursor,
    )


def create_running_job(session: Session) -> tuple[CollectionJob, CollectionAttempt]:
    keyword = Keyword(
        keyword_text=f"raw evidence {uuid.uuid4()}",
        normalized_text=f"raw evidence {uuid.uuid4()}",
        marketplace=Marketplace.AMAZON_IN,
        tier=TrackingTier.T1,
        tracking_status=KeywordTrackingStatus.ACTIVE,
        intent_cluster=IntentCluster.GENERIC_CATEGORY,
    )
    session.add(keyword)
    session.flush()
    job = CollectionJob(
        idempotency_key=f"source-evidence:{keyword.id}",
        job_type=CollectionJobType.SERP,
        source_tier=CollectionSourceTier.FIRST_PARTY_API,
        platform=SourceType.AMAZON_SP_API.value,
        keyword_id=keyword.id,
        status=CollectionJobStatus.RUNNING,
        scheduled_for=CAPTURED_AT,
        attempt_count=1,
        started_at=CAPTURED_AT,
    )
    attempt = CollectionAttempt(
        job=job,
        attempt_number=1,
        status=CollectionAttemptStatus.RUNNING,
        started_at=CAPTURED_AT,
    )
    session.add_all((job, attempt))
    session.commit()
    return job, attempt


def add_running_attempt(session: Session, job: CollectionJob) -> CollectionAttempt:
    attempt = CollectionAttempt(
        job_id=job.id,
        attempt_number=2,
        status=CollectionAttemptStatus.RUNNING,
        started_at=CAPTURED_AT,
    )
    session.add(attempt)
    session.commit()
    return attempt


def make_bridge(
    engine: Engine,
    adapter: FakeAdapter,
    store: MemoryStore,
    *,
    factory: sessionmaker[Session] | None = None,
) -> SourceRawEvidenceBridge:
    return SourceRawEvidenceBridge(
        adapter=adapter,
        object_store=store,
        session_factory=factory or sessionmaker(bind=engine, expire_on_commit=False),
    )


@pytest.mark.asyncio
async def test_one_raw_page_is_persisted_with_exact_lineage(engine: Engine) -> None:
    body = b'{"asin":"B000TEST01"}'
    store = MemoryStore()
    bridge = make_bridge(engine, FakeAdapter((raw_page(body, fingerprint="request-1"),)), store)
    with Session(engine, expire_on_commit=False) as session:
        job, attempt = create_running_job(session)

    result = await bridge.execute(
        job_id=job.id,
        attempt_id=attempt.id,
        request=SYNC_REQUEST,
        captured_at=CAPTURED_AT,
    )

    assert store.calls == [("amazon_sp_api", "catalog_items", body)]
    assert result.metadata["raw_page_count"] == 1
    assert result.metadata["raw_evidence_id"] == result.metadata["raw_evidence_ids"][0]
    with Session(engine) as session:
        evidence = session.scalars(select(RawEvidence)).one()
        assert evidence.job_id == job.id
        assert evidence.attempt_id == attempt.id
        assert evidence.sha256 == hashlib.sha256(body).hexdigest()
        assert evidence.content_type == "application/json"
        assert evidence.final_url is None
        assert evidence.challenge_detected is False
        assert evidence.capture_metadata == {
            "source_type": "amazon_sp_api",
            "resource_type": "catalog_items",
            "request_fingerprint": "request-1",
            "page_index": 0,
            "compressed_byte_length": 10,
        }
        assert session.query(ParserVersion).count() == 0
        assert session.query(DataQualityCheck).count() == 0


@pytest.mark.asyncio
async def test_multiple_pages_are_persisted_once_in_deterministic_order(engine: Engine) -> None:
    pages = (
        raw_page(b"page-1", fingerprint="request-1", next_cursor={"token": "next"}),
        raw_page(b"page-2", fingerprint="request-2"),
    )
    store = MemoryStore()
    bridge = make_bridge(engine, FakeAdapter(pages), store)
    with Session(engine, expire_on_commit=False) as session:
        job, attempt = create_running_job(session)

    result = await bridge.execute(job_id=job.id, attempt_id=attempt.id, request=SYNC_REQUEST)

    assert [call[2] for call in store.calls] == [b"page-1", b"page-2"]
    assert result.metadata["raw_page_count"] == 2
    evidence_ids = [uuid.UUID(value) for value in result.metadata["raw_evidence_ids"]]
    with Session(engine) as session:
        evidence = [session.get(RawEvidence, evidence_id) for evidence_id in evidence_ids]
        assert all(item is not None for item in evidence)
        assert [item.capture_metadata["page_index"] for item in evidence if item] == [0, 1]
        assert evidence[0].capture_metadata["next_cursor"] == {"token": "next"}  # type: ignore[union-attr]
        assert evidence[1].attempt_id == attempt.id  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_identical_content_keeps_separate_attempt_lineage(engine: Engine) -> None:
    store = MemoryStore()
    bridge = make_bridge(
        engine,
        FakeAdapter((raw_page(b"same-body", fingerprint="same-request"),)),
        store,
    )
    with Session(engine, expire_on_commit=False) as session:
        job, first_attempt = create_running_job(session)
        second_attempt = add_running_attempt(session, job)

    first = await bridge.execute(
        job_id=job.id, attempt_id=first_attempt.id, request=SYNC_REQUEST
    )
    second = await bridge.execute(
        job_id=job.id, attempt_id=second_attempt.id, request=SYNC_REQUEST
    )

    assert first.metadata["raw_evidence_id"] != second.metadata["raw_evidence_id"]
    with Session(engine) as session:
        evidence = session.scalars(select(RawEvidence).order_by(RawEvidence.created_at)).all()
        assert len(evidence) == 2
        assert evidence[0].sha256 == evidence[1].sha256
        assert evidence[0].object_key == evidence[1].object_key
        assert {item.attempt_id for item in evidence} == {first_attempt.id, second_attempt.id}


@pytest.mark.asyncio
async def test_same_body_keeps_different_request_fingerprints(engine: Engine) -> None:
    store = MemoryStore()
    with Session(engine, expire_on_commit=False) as session:
        job, attempt = create_running_job(session)

    for fingerprint in ("logical-request-a", "logical-request-b"):
        bridge = make_bridge(
            engine,
            FakeAdapter((raw_page(b"same-body", fingerprint=fingerprint),)),
            store,
        )
        await bridge.execute(job_id=job.id, attempt_id=attempt.id, request=SYNC_REQUEST)

    with Session(engine) as session:
        evidence = session.scalars(select(RawEvidence).order_by(RawEvidence.created_at)).all()
        assert evidence[0].sha256 == evidence[1].sha256
        assert [item.capture_metadata["request_fingerprint"] for item in evidence] == [
            "logical-request-a",
            "logical-request-b",
        ]


@pytest.mark.asyncio
async def test_storage_failure_creates_no_false_evidence(engine: Engine) -> None:
    bridge = make_bridge(
        engine,
        FakeAdapter((raw_page(b"fails", fingerprint="request-fail"),)),
        MemoryStore(fail_at=0),
    )
    with Session(engine, expire_on_commit=False) as session:
        job, attempt = create_running_job(session)

    with pytest.raises(CollectionExecutionError) as raised:
        await bridge.execute(job_id=job.id, attempt_id=attempt.id, request=SYNC_REQUEST)

    assert raised.value.failure_type is CollectionFailureType.STORAGE_ERROR
    assert raised.value.code == "raw_storage_failed"
    assert raised.value.retryable is True
    assert raised.value.details["persisted_page_count"] == 0
    assert "must-not-leak" not in str(raised.value)
    assert "must-not-leak" not in repr(raised.value.details)
    with Session(engine) as session:
        assert session.query(RawEvidence).count() == 0


@pytest.mark.asyncio
async def test_partial_multi_page_failure_retains_prior_durable_page(engine: Engine) -> None:
    bridge = make_bridge(
        engine,
        FakeAdapter(
            (
                raw_page(b"durable", fingerprint="request-1"),
                raw_page(b"fails", fingerprint="request-2"),
            )
        ),
        MemoryStore(fail_at=1),
    )
    with Session(engine, expire_on_commit=False) as session:
        job, attempt = create_running_job(session)

    with pytest.raises(CollectionExecutionError) as raised:
        await bridge.execute(job_id=job.id, attempt_id=attempt.id, request=SYNC_REQUEST)

    assert raised.value.details["failed_page_index"] == 1
    assert raised.value.details["persisted_page_count"] == 1
    assert len(raised.value.details["persisted_raw_evidence_ids"]) == 1
    with Session(engine) as session:
        evidence = session.scalars(select(RawEvidence)).one()
        assert evidence.sha256 == hashlib.sha256(b"durable").hexdigest()
        assert session.query(ParserVersion).count() == 0


@pytest.mark.asyncio
async def test_database_failure_does_not_return_success(engine: Engine) -> None:
    class FailingCommitSession(Session):
        def commit(self) -> None:
            raise RuntimeError("database unavailable with secret=must-not-leak")

    failing_factory = sessionmaker(
        bind=engine,
        class_=FailingCommitSession,
        expire_on_commit=False,
    )
    bridge = make_bridge(
        engine,
        FakeAdapter((raw_page(b"db-fail", fingerprint="request-db"),)),
        MemoryStore(),
        factory=failing_factory,
    )
    with Session(engine, expire_on_commit=False) as session:
        job, attempt = create_running_job(session)

    with pytest.raises(CollectionExecutionError) as raised:
        await bridge.execute(job_id=job.id, attempt_id=attempt.id, request=SYNC_REQUEST)

    assert raised.value.failure_type is CollectionFailureType.STORAGE_ERROR
    assert raised.value.code == "raw_evidence_persistence_failed"
    assert raised.value.retryable is True
    assert "must-not-leak" not in str(raised.value)
    assert "must-not-leak" not in repr(raised.value.details)
    with Session(engine) as session:
        assert session.query(RawEvidence).count() == 0


@pytest.mark.asyncio
async def test_source_errors_are_mapped_without_secret_material(engine: Engine) -> None:
    secret = "fake-access-token-123"
    bridge = make_bridge(
        engine,
        FakeAdapter(error=FakeSourceError(f"rejected token {secret}")),
        MemoryStore(),
    )
    with Session(engine, expire_on_commit=False) as session:
        job, attempt = create_running_job(session)

    with pytest.raises(CollectionExecutionError) as raised:
        await bridge.execute(job_id=job.id, attempt_id=attempt.id, request=SYNC_REQUEST)

    assert raised.value.failure_type is CollectionFailureType.UNKNOWN
    assert raised.value.code == "source_adapter_failed"
    assert raised.value.retryable is False
    assert secret not in str(raised.value)
    assert secret not in repr(raised.value.details)


@pytest.mark.asyncio
async def test_injected_source_error_mapper_is_honored(engine: Engine) -> None:
    secret = "fake-refresh-token-456"
    mapper_calls: list[Exception] = []

    def error_mapper(error: Exception) -> CollectionExecutionError:
        mapper_calls.append(error)
        return CollectionExecutionError(
            "Configured source retry is required",
            failure_type=CollectionFailureType.NETWORK,
            code="configured_source_retry",
            retryable=True,
            details={"source": "fake"},
        )

    bridge = SourceRawEvidenceBridge(
        adapter=FakeAdapter(error=FakeSourceError(f"request failed {secret}")),
        object_store=MemoryStore(),
        session_factory=sessionmaker(bind=engine, expire_on_commit=False),
        error_mapper=error_mapper,
    )
    with Session(engine, expire_on_commit=False) as session:
        job, attempt = create_running_job(session)

    with pytest.raises(CollectionExecutionError) as raised:
        await bridge.execute(job_id=job.id, attempt_id=attempt.id, request=SYNC_REQUEST)

    assert len(mapper_calls) == 1
    assert raised.value.failure_type is CollectionFailureType.NETWORK
    assert raised.value.code == "configured_source_retry"
    assert raised.value.retryable is True
    assert secret not in str(raised.value)
    assert secret not in repr(raised.value.details)
