from __future__ import annotations

import hashlib
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from novel_signal.collectors.base import CaptureRequest, CaptureResult
from novel_signal.db import Base
from novel_signal.modules.collection.execution import CollectionExecutionError
from novel_signal.modules.collection.models import (
    CollectionJob,
    CollectionJobStatus,
    CollectionJobType,
    CollectionSourceTier,
    DataQualityCheck,
    ParserVersion,
    QuarantineRecord,
    RawEvidence,
)
from novel_signal.modules.collection.parsing import EnvelopeValidator, ParserRegistry
from novel_signal.modules.collection.pipeline import EvidencePipeline, PublishContext
from novel_signal.modules.collection.service import CollectionLifecycleService
from novel_signal.modules.collection.storage import StoredRawObject
from novel_signal.modules.keywords.models import IntentCluster, Keyword, KeywordTrackingStatus
from novel_signal.modules.universe.models import Marketplace, TrackingTier
from novel_signal.parsers.base import ParsedEnvelope
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


class MemoryStore:
    def __init__(self) -> None:
        self.calls: list[bytes] = []

    def put_raw(self, *, platform: str, page_type: str, body: bytes) -> StoredRawObject:
        self.calls.append(body)
        digest = hashlib.sha256(body).hexdigest()
        return StoredRawObject(
            sha256=digest,
            bucket="test-raw",
            object_key=f"raw/{platform}/{page_type}/{digest}.gz",
            byte_length=len(body),
            compressed_byte_length=max(1, len(body) // 2),
        )


class FixedParser:
    platform = "amazon_in"
    page_type = "serp"
    version = "serp-v1"

    def __init__(self, records: tuple[dict[str, Any], ...], store: MemoryStore) -> None:
        self.records = records
        self.store = store
        self.calls = 0

    def parse(self, raw: bytes) -> ParsedEnvelope:
        self.calls += 1
        assert self.store.calls, "raw evidence must be stored before parser execution"
        return ParsedEnvelope(
            parser_version=self.version,
            page_type=self.page_type,
            records=self.records,
        )


class BrokenParser(FixedParser):
    def parse(self, raw: bytes) -> ParsedEnvelope:
        assert self.store.calls, "raw evidence must be stored before parser execution"
        raise ValueError("seeded parser break")


class RecordingPublisher:
    def __init__(self) -> None:
        self.calls: list[tuple[PublishContext, tuple[dict[str, Any], ...]]] = []

    def publish(
        self,
        context: PublishContext,
        records: tuple[dict[str, Any], ...],
    ) -> dict[str, Any]:
        self.calls.append((context, records))
        return {"sink": "recording"}


def running_job(session: Session) -> tuple[CollectionJob, Any]:
    keyword = Keyword(
        keyword_text="baby diapers",
        normalized_text="baby diapers",
        marketplace=Marketplace.AMAZON_IN,
        tier=TrackingTier.T1,
        tracking_status=KeywordTrackingStatus.ACTIVE,
        intent_cluster=IntentCluster.GENERIC_CATEGORY,
    )
    session.add(keyword)
    session.flush()
    job = CollectionJob(
        idempotency_key=f"pipeline:{keyword.id}",
        job_type=CollectionJobType.SERP,
        source_tier=CollectionSourceTier.PUBLIC_PAGE,
        platform="amazon_in",
        keyword_id=keyword.id,
        scheduled_for=datetime(2026, 8, 17, 6, 0, tzinfo=UTC),
    )
    session.add(job)
    session.commit()
    claim = CollectionLifecycleService(session).claim_attempt(job.id, at=job.scheduled_for)
    assert claim is not None
    session.commit()
    return job, claim


def make_pipeline(engine: Engine, parser: FixedParser, store: MemoryStore) -> EvidencePipeline:
    registry = ParserRegistry()
    registry.register(parser)
    return EvidencePipeline(
        parser_registry=registry,
        object_store=store,
        session_factory=sessionmaker(bind=engine, expire_on_commit=False),
    )


def test_valid_capture_is_raw_first_validated_and_published(engine: Engine) -> None:
    store = MemoryStore()
    parser = FixedParser(({"position": 1, "asin": "B0001"},), store)
    publisher = RecordingPublisher()
    pipeline = make_pipeline(engine, parser, store)

    with Session(engine, expire_on_commit=False) as session:
        job, claim = running_job(session)

    result = pipeline.process(
        job_id=job.id,
        attempt_id=claim.attempt.id,
        platform="amazon_in",
        request=CaptureRequest(url="https://example.test/s", target_id="kw-1", page_type="serp"),
        capture=CaptureResult(
            final_url="https://example.test/s",
            body=b"<html>valid</html>",
            content_type="text/html",
        ),
        validator=EnvelopeValidator(required_fields=("position", "asin")),
        publisher=publisher,
    )

    assert result.quarantine is None
    assert result.metadata["row_count"] == 1
    assert parser.calls == 1
    assert len(publisher.calls) == 1
    with Session(engine) as session:
        evidence = session.scalars(select(RawEvidence)).all()
        versions = session.scalars(select(ParserVersion)).all()
        checks = session.scalars(select(DataQualityCheck)).all()
        assert len(evidence) == 1
        assert evidence[0].sha256 == hashlib.sha256(b"<html>valid</html>").hexdigest()
        assert len(versions) == 1
        assert versions[0].version == "serp-v1"
        assert len(checks) == 2


def test_validation_failure_returns_quarantine_and_never_publishes(engine: Engine) -> None:
    store = MemoryStore()
    parser = FixedParser(({"position": 1},), store)
    publisher = RecordingPublisher()
    pipeline = make_pipeline(engine, parser, store)

    with Session(engine, expire_on_commit=False) as session:
        job, claim = running_job(session)

    result = pipeline.process(
        job_id=job.id,
        attempt_id=claim.attempt.id,
        platform="amazon_in",
        request=CaptureRequest(url="https://example.test/s", target_id="kw-1", page_type="serp"),
        capture=CaptureResult(
            final_url="https://example.test/s",
            body=b"<html>missing asin</html>",
            content_type="text/html",
        ),
        validator=EnvelopeValidator(required_fields=("position", "asin")),
        publisher=publisher,
    )

    assert result.quarantine is not None
    assert result.quarantine.reason_code == "schema_validation_failed"
    assert publisher.calls == []
    with Session(engine) as session:
        raw = session.get(RawEvidence, result.quarantine.raw_evidence_id)
        parser_version = session.get(ParserVersion, result.quarantine.parser_version_id)
        assert raw is not None
        assert parser_version is not None
        lifecycle = CollectionLifecycleService(session)
        lifecycle.mark_quarantined(
            job.id,
            claim.attempt.id,
            raw_evidence=raw,
            parser_version=parser_version,
            failure_type=result.quarantine.failure_type,
            reason_code=result.quarantine.reason_code,
            reason=result.quarantine.reason,
            schema_errors=list(result.quarantine.schema_errors),
            parsed_payload=result.quarantine.parsed_payload,
        )
        session.commit()
        assert session.get(CollectionJob, job.id).status is CollectionJobStatus.QUARANTINED  # type: ignore[union-attr]
        assert session.query(QuarantineRecord).count() == 1


def test_parser_exception_is_quarantined_with_raw_retained(engine: Engine) -> None:
    store = MemoryStore()
    parser = BrokenParser((), store)
    publisher = RecordingPublisher()
    pipeline = make_pipeline(engine, parser, store)

    with Session(engine, expire_on_commit=False) as session:
        job, claim = running_job(session)

    result = pipeline.process(
        job_id=job.id,
        attempt_id=claim.attempt.id,
        platform="amazon_in",
        request=CaptureRequest(url="https://example.test/s", target_id="kw-1", page_type="serp"),
        capture=CaptureResult(
            final_url="https://example.test/s",
            body=b"<html>changed layout</html>",
            content_type="text/html",
        ),
        validator=EnvelopeValidator(required_fields=("position",)),
        publisher=publisher,
    )

    assert result.quarantine is not None
    assert result.quarantine.reason_code == "parser_exception"
    assert publisher.calls == []
    with Session(engine) as session:
        assert session.query(RawEvidence).count() == 1
        assert session.query(DataQualityCheck).count() == 1


def test_challenge_stops_after_raw_evidence_and_does_not_parse(engine: Engine) -> None:
    store = MemoryStore()
    parser = FixedParser(({"position": 1},), store)
    pipeline = make_pipeline(engine, parser, store)

    with Session(engine, expire_on_commit=False) as session:
        job, claim = running_job(session)

    with pytest.raises(CollectionExecutionError) as exc_info:
        pipeline.process(
            job_id=job.id,
            attempt_id=claim.attempt.id,
            platform="amazon_in",
            request=CaptureRequest(
                url="https://example.test/challenge", target_id="kw-1", page_type="serp"
            ),
            capture=CaptureResult(
                final_url="https://example.test/challenge",
                body=b"captcha",
                content_type="text/html",
                challenge_detected=True,
            ),
            validator=EnvelopeValidator(required_fields=("position",)),
            publisher=RecordingPublisher(),
        )

    assert exc_info.value.code == "challenge_detected"
    assert parser.calls == 0
    with Session(engine) as session:
        evidence = session.scalars(select(RawEvidence)).one()
        assert evidence.challenge_detected is True


def test_raw_storage_failure_prevents_parser_execution(engine: Engine) -> None:
    class FailingStore(MemoryStore):
        def put_raw(self, *, platform: str, page_type: str, body: bytes) -> StoredRawObject:
            raise OSError("object store unavailable")

    store = FailingStore()
    parser = FixedParser(({"position": 1},), store)
    pipeline = make_pipeline(engine, parser, store)
    with Session(engine, expire_on_commit=False) as session:
        job, claim = running_job(session)

    with pytest.raises(CollectionExecutionError) as exc_info:
        pipeline.process(
            job_id=job.id,
            attempt_id=claim.attempt.id,
            platform="amazon_in",
            request=CaptureRequest(
                url="https://example.test/s",
                target_id="kw-1",
                page_type="serp",
            ),
            capture=CaptureResult(
                final_url="https://example.test/s",
                body=b"raw",
                content_type="text/html",
            ),
            validator=EnvelopeValidator(),
            publisher=RecordingPublisher(),
        )
    assert exc_info.value.code == "raw_storage_failed"
    assert parser.calls == 0
    with Session(engine) as session:
        assert session.query(RawEvidence).count() == 0
