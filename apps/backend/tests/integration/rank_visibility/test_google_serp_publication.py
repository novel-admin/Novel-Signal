from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from novel_signal.db import Base
from novel_signal.modules.collection.models import (
    CollectionJob,
    CollectionJobType,
    CollectionSourceTier,
    ParserVersion,
    RawEvidence,
)
from novel_signal.modules.collection.pipeline import PublishContext
from novel_signal.modules.collection.service import CollectionLifecycleService
from novel_signal.modules.keywords.models import IntentCluster, Keyword, KeywordTrackingStatus
from novel_signal.modules.rank_visibility.errors import RankVisibilityConflictError
from novel_signal.modules.rank_visibility.google_publication import (
    GoogleSerpPublicationConfig,
    GoogleSerpPublisher,
)
from novel_signal.modules.rank_visibility.google_visibility import GoogleVisibilityService
from novel_signal.modules.rank_visibility.models import (
    DeviceProfile,
    GoogleSerpCapture,
    GoogleSerpResult,
)
from novel_signal.modules.universe.models import Marketplace, TrackingTier
from sqlalchemy import Engine, create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

CAPTURED_AT = datetime(2026, 8, 26, 8, 0, tzinfo=UTC)


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


def _setup(engine: Engine) -> tuple[sessionmaker[Session], Keyword, PublishContext]:
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
        session.add(keyword)
        session.flush()
        job = CollectionJob(
            idempotency_key=f"google:serp:{keyword.id}",
            job_type=CollectionJobType.SERP,
            source_tier=CollectionSourceTier.PUBLIC_PAGE,
            platform="google",
            keyword_id=keyword.id,
            scheduled_for=CAPTURED_AT,
        )
        session.add(job)
        session.commit()
        claim = CollectionLifecycleService(session).claim_attempt(job.id, at=CAPTURED_AT)
        assert claim is not None
        parser = ParserVersion(platform="google", page_type="serp", version="google-serp-v1")
        raw = RawEvidence(
            job_id=job.id,
            attempt_id=claim.attempt.id,
            sha256="a" * 64,
            storage_bucket="raw",
            object_key="google/a.gz",
            content_type="text/html",
            byte_length=100,
            captured_at=CAPTURED_AT,
        )
        session.add_all([parser, raw])
        session.commit()
        return (
            factory,
            keyword,
            PublishContext(
                job_id=job.id,
                attempt_id=claim.attempt.id,
                raw_evidence_id=raw.id,
                parser_version_id=parser.id,
                platform="google",
                page_type="serp",
                captured_at=CAPTURED_AT,
            ),
        )


def _records(*, title: str = "Novel Wipes") -> tuple[dict[str, object], ...]:
    return (
        {
            "absolute_position": 1,
            "page_number": 1,
            "query": "baby wipes",
            "result_type": "organic",
            "title": title,
            "url": "https://www.novel.example/wipes?size=80",
            "displayed_domain": "novel.example",
            "snippet": "Soft baby wipes",
            "identity_match": "novel",
            "identity_domain": "novel.example",
            "result_metadata": {"destination_host": "novel.example"},
        },
        {
            "absolute_position": 2,
            "page_number": 1,
            "query": "baby wipes",
            "result_type": "organic",
            "title": "Competitor Wipes",
            "url": "https://shop.acme.example/wipes",
            "displayed_domain": "shop.acme.example",
            "snippet": None,
            "identity_match": "competitor",
            "identity_domain": "acme.example",
            "result_metadata": {"destination_host": "acme.example"},
        },
    )


def _publisher(factory: sessionmaker[Session], keyword: Keyword) -> GoogleSerpPublisher:
    return GoogleSerpPublisher(
        config=GoogleSerpPublicationConfig(
            keyword_id=keyword.id,
            geo_code="IN",
            device_profile=DeviceProfile.DESKTOP,
            query=keyword.keyword_text,
            profile_id="google-desktop-in",
        ),
        session_factory=factory,
    )


def test_publication_preserves_lineage_and_supports_rank_history(engine: Engine) -> None:
    factory, keyword, context = _setup(engine)
    result = _publisher(factory, keyword).publish(context, _records())

    assert result["publication"] == "created"
    with factory() as session:
        capture = session.scalars(select(GoogleSerpCapture)).one()
        assert capture.keyword_id == keyword.id
        assert capture.source_job_id == context.job_id
        assert capture.raw_evidence_id == context.raw_evidence_id
        assert capture.parser_version_id == context.parser_version_id
        assert capture.parser_version == "google-serp-v1"
        assert capture.result_count == 2
        assert capture.capture_metadata is not None
        assert capture.capture_metadata["attempt_id"] == str(context.attempt_id)
        assert "requested_url" not in capture.capture_metadata
        assert "<html" not in str(capture.capture_metadata).lower()
        service = GoogleVisibilityService(session)
        history = service.history(
            keyword_id=keyword.id,
            domain="novel.example",
            geo_code="IN",
            device_profile=DeviceProfile.DESKTOP,
            from_at=CAPTURED_AT - timedelta(minutes=1),
            to_at=CAPTURED_AT + timedelta(minutes=1),
        )
        assert [row.absolute_position for row, _ in history] == [1]
        assert service.latest_rank(keyword_id=keyword.id, domain="novel.example") is not None


def test_exact_replay_is_idempotent_and_conflicting_replay_is_rejected(engine: Engine) -> None:
    factory, keyword, context = _setup(engine)
    publisher = _publisher(factory, keyword)
    first = publisher.publish(context, _records())
    replay = publisher.publish(context, _records())
    assert replay["publication"] == "existing"
    assert replay["capture_id"] == first["capture_id"]

    with pytest.raises(RankVisibilityConflictError):
        publisher.publish(context, _records(title="Conflicting title"))
    with factory() as session:
        assert len(session.scalars(select(GoogleSerpCapture)).all()) == 1
        assert len(session.scalars(select(GoogleSerpResult)).all()) == 2


def test_distinct_raw_evidence_creates_history(engine: Engine) -> None:
    factory, keyword, context = _setup(engine)
    publisher = _publisher(factory, keyword)
    first = publisher.publish(context, _records())
    with factory() as session:
        raw = RawEvidence(
            job_id=context.job_id,
            attempt_id=context.attempt_id,
            sha256="b" * 64,
            storage_bucket="raw",
            object_key="google/b.gz",
            content_type="text/html",
            byte_length=101,
            captured_at=CAPTURED_AT + timedelta(minutes=5),
        )
        session.add(raw)
        session.commit()
        second_context = PublishContext(
            **{
                **context.__dict__,
                "raw_evidence_id": raw.id,
                "captured_at": CAPTURED_AT + timedelta(minutes=5),
            }
        )
    second = publisher.publish(second_context, _records())
    assert first["ingestion_key"] != second["ingestion_key"]
    with factory() as session:
        assert len(session.scalars(select(GoogleSerpCapture)).all()) == 2


@pytest.mark.parametrize("missing", ["raw", "parser"])
def test_missing_publication_lineage_is_rejected(engine: Engine, missing: str) -> None:
    factory, keyword, context = _setup(engine)
    values = context.__dict__.copy()
    values[f"{missing}_evidence_id" if missing == "raw" else "parser_version_id"] = uuid4()
    if missing == "raw":
        values["raw_evidence_id"] = values.pop("raw_evidence_id", uuid4())
    with pytest.raises(ValueError, match="unavailable"):
        _publisher(factory, keyword).publish(PublishContext(**values), _records())


def test_mismatched_attempt_zero_rows_and_raw_metadata_are_rejected(engine: Engine) -> None:
    factory, keyword, context = _setup(engine)
    publisher = _publisher(factory, keyword)
    with pytest.raises(ValueError, match="at least one"):
        publisher.publish(context, ())
    with pytest.raises(ValueError, match="lineage"):
        publisher.publish(PublishContext(**{**context.__dict__, "attempt_id": uuid4()}), _records())
    unsafe = list(_records())
    unsafe[0] = {**unsafe[0], "result_metadata": {"raw_html": "<html>secret</html>"}}
    with pytest.raises(ValueError, match="raw HTML"):
        publisher.publish(context, tuple(unsafe))
