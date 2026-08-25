from __future__ import annotations

import hashlib
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from novel_signal.collectors.base import CaptureRequest, CaptureResult
from novel_signal.db import Base
from novel_signal.modules.collection.execution import CollectionExecutionError
from novel_signal.modules.collection.models import (
    CollectionJob,
    CollectionJobType,
    CollectionSourceTier,
    ParserVersion,
    RawEvidence,
)
from novel_signal.modules.collection.parsing import EnvelopeValidator, ParserRegistry
from novel_signal.modules.collection.pipeline import EvidencePipeline
from novel_signal.modules.collection.service import AttemptClaim, CollectionLifecycleService
from novel_signal.modules.collection.storage import StoredRawObject
from novel_signal.modules.keywords.models import IntentCluster, Keyword, KeywordTrackingStatus
from novel_signal.modules.rank_visibility.models import (
    BadgeEvent,
    DeviceProfile,
    NewEntrantEvent,
    SerpCapture,
)
from novel_signal.modules.rank_visibility.publication import (
    AmazonSerpPublicationConfig,
    AmazonSerpPublisher,
)
from novel_signal.modules.universe.models import (
    Competitor,
    CompetitorProduct,
    Marketplace,
    PositioningTier,
    Product,
    TrackingTier,
)
from novel_signal.parsers.amazon_serp import AmazonSerpParser
from sqlalchemy import Engine, create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

CAPTURED_AT = datetime(2026, 8, 25, 6, 0, tzinfo=UTC)
REQUEST_URL = "https://www.amazon.in/s?k=baby+wipes"
BODY = b"""
<div data-component-type="s-search-result" data-asin="B0OWN00001" data-brand="Novel">
  <h2>Novel Baby Wipes</h2><span>Best Seller</span><span>Rs. 199</span>
</div>
<div data-component-type="s-search-result" data-asin="B0COMP0001" data-brand="Acme">
  <h2>Acme Baby Wipes</h2><span>Sponsored</span><span>Deal</span><span>Rs. 149</span>
</div>
<div data-component-type="s-search-result" data-asin="B0OTHER001" data-brand="Other">
  <h2>Other Baby Wipes</h2><span>Rs. 179</span>
</div>
"""
SECOND_BODY = BODY.replace(b"Other Baby Wipes", b"Other Wipes Updated")


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


class RawFirstAmazonSerpParser(AmazonSerpParser):
    def __init__(self, store: MemoryStore) -> None:
        super().__init__()
        self.store = store

    def parse(self, raw: bytes):  # type: ignore[no-untyped-def]
        assert self.store.calls, "raw evidence must be stored before parser execution"
        return super().parse(raw)


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


def _setup(
    engine: Engine,
) -> tuple[EvidencePipeline, AmazonSerpPublisher, CollectionJob, AttemptClaim]:
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
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
            marketplace_product_id="B0OWN00001",
            tracking_tier=TrackingTier.T1,
        )
        competitor = Competitor(name="Acme", positioning_tier=PositioningTier.MID)
        competitor_product = CompetitorProduct(
            competitor=competitor,
            name="Acme wipes",
            brand="Acme",
            category="Wipes",
            marketplace=Marketplace.AMAZON_IN,
            marketplace_product_id="B0COMP0001",
            tracking_tier=TrackingTier.T1,
        )
        session.add_all([keyword, product, competitor_product])
        session.flush()
        job = CollectionJob(
            idempotency_key=f"amazon-serp:{keyword.id}",
            job_type=CollectionJobType.SERP,
            source_tier=CollectionSourceTier.PUBLIC_PAGE,
            platform="amazon_in",
            keyword_id=keyword.id,
            scheduled_for=CAPTURED_AT,
        )
        session.add(job)
        session.commit()
        claim = CollectionLifecycleService(session).claim_attempt(job.id, at=CAPTURED_AT)
        assert claim is not None
        session.commit()

    store = MemoryStore()
    registry = ParserRegistry()
    registry.register(RawFirstAmazonSerpParser(store))
    pipeline = EvidencePipeline(
        parser_registry=registry,
        object_store=store,
        session_factory=factory,
    )
    publisher = AmazonSerpPublisher(
        config=AmazonSerpPublicationConfig(
            keyword_id=keyword.id,
            geo_code="570001",
            device_profile=DeviceProfile.DESKTOP,
            query="baby wipes",
            page_number=1,
            profile_id="desktop-mysore",
            pincode="570001",
            location_label="Mysore",
        ),
        session_factory=factory,
    )
    return pipeline, publisher, job, claim


def _process(
    pipeline: EvidencePipeline,
    publisher: AmazonSerpPublisher,
    job: CollectionJob,
    claim: AttemptClaim,
    body: bytes,
    *,
    captured_at: datetime = CAPTURED_AT,
    challenge_detected: bool = False,
):
    return pipeline.process(
        job_id=job.id,
        attempt_id=claim.attempt.id,
        platform="amazon_in",
        request=CaptureRequest(url=REQUEST_URL, target_id=str(job.keyword_id), page_type="serp"),
        capture=CaptureResult(
            final_url=REQUEST_URL,
            body=body,
            content_type="text/html",
            challenge_detected=challenge_detected,
        ),
        validator=EnvelopeValidator(
            required_fields=(
                "absolute_position",
                "page_number",
                "marketplace_product_id",
                "placement_type",
                "badges",
            )
        ),
        publisher=publisher,
        captured_at=captured_at,
    )


def test_amazon_serp_raw_evidence_publishes_to_s3(engine: Engine) -> None:
    pipeline, publisher, job, claim = _setup(engine)

    result = _process(pipeline, publisher, job, claim, BODY)

    assert result.quarantine is None
    assert result.metadata["publication"] == "created"
    with Session(engine) as session:
        evidence = session.scalars(select(RawEvidence)).all()
        parser_version = session.scalars(select(ParserVersion)).one()
        capture = session.scalars(select(SerpCapture)).one()
        assert len(evidence) == 1
        assert parser_version.version == "amazon-serp-v1"
        assert capture.source_job_id == str(job.id)
        assert capture.parser_version == parser_version.version
        assert capture.captured_at.replace(tzinfo=UTC) == CAPTURED_AT
        assert capture.result_count == 3
        assert capture.capture_metadata == {
            "raw_evidence_id": str(evidence[0].id),
            "parser_version_id": str(parser_version.id),
            "platform": "amazon_in",
            "page_type": "serp",
            "query": "baby wipes",
            "page_number": 1,
            "final_url": REQUEST_URL,
            "requested_url": REQUEST_URL,
            "profile_id": "desktop-mysore",
            "pincode": "570001",
            "location_label": "Mysore",
        }
        assert BODY.decode() not in str(capture.capture_metadata)
        assert capture.results[0].product_id is not None
        assert capture.results[1].competitor_product_id is not None
        assert capture.results[2].product_id is None
        assert capture.results[2].competitor_product_id is None


def test_exact_raw_replay_is_idempotent_without_duplicate_s3_events(engine: Engine) -> None:
    pipeline, publisher, job, claim = _setup(engine)
    first = _process(pipeline, publisher, job, claim, BODY)
    raw_evidence_id = UUID(str(first.metadata["raw_evidence_id"]))

    replay = pipeline.process_persisted_raw(
        job_id=job.id,
        attempt_id=claim.attempt.id,
        raw_evidence_id=raw_evidence_id,
        platform="amazon_in",
        page_type="serp",
        body=BODY,
        validator=EnvelopeValidator(
            required_fields=(
                "absolute_position",
                "page_number",
                "marketplace_product_id",
                "placement_type",
                "badges",
            )
        ),
        publisher=publisher,
        captured_at=CAPTURED_AT,
    )

    assert replay.quarantine is None
    assert replay.metadata["publication"] == "existing"
    assert replay.metadata["capture_id"] == first.metadata["capture_id"]
    with Session(engine) as session:
        assert len(session.scalars(select(SerpCapture)).all()) == 1
        assert len(session.scalars(select(BadgeEvent)).all()) == 3
        assert len(session.scalars(select(NewEntrantEvent)).all()) == 3


def test_different_raw_evidence_creates_a_distinct_s3_capture(engine: Engine) -> None:
    pipeline, publisher, job, claim = _setup(engine)
    first = _process(pipeline, publisher, job, claim, BODY)
    second = _process(
        pipeline,
        publisher,
        job,
        claim,
        SECOND_BODY,
        captured_at=CAPTURED_AT + timedelta(minutes=5),
    )

    assert first.metadata["ingestion_key"] != second.metadata["ingestion_key"]
    with Session(engine) as session:
        assert len(session.scalars(select(RawEvidence)).all()) == 2
        assert len(session.scalars(select(SerpCapture)).all()) == 2


def test_challenge_raw_evidence_is_retained_without_s3_capture(engine: Engine) -> None:
    pipeline, publisher, job, claim = _setup(engine)

    with pytest.raises(CollectionExecutionError, match="Marketplace challenge") as raised:
        _process(pipeline, publisher, job, claim, BODY, challenge_detected=True)

    assert raised.value.code == "challenge_detected"
    with Session(engine) as session:
        assert len(session.scalars(select(RawEvidence)).all()) == 1
        assert session.scalars(select(SerpCapture)).all() == []


def test_invalid_amazon_serp_envelope_is_quarantined_without_s3_capture(engine: Engine) -> None:
    pipeline, publisher, job, claim = _setup(engine)

    result = _process(pipeline, publisher, job, claim, b"<html>no product cards</html>")

    assert result.quarantine is not None
    assert result.quarantine.reason_code == "schema_validation_failed"
    with Session(engine) as session:
        assert len(session.scalars(select(RawEvidence)).all()) == 1
        assert session.scalars(select(SerpCapture)).all() == []
