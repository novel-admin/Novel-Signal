from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from novel_signal.db import Base, get_db
from novel_signal.main import app
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


def _add_google_capture(
    session: Session,
    *,
    keyword: Keyword,
    context: PublishContext,
    key: str,
    captured_at: datetime,
    domains: list[str],
    geo_code: str = "IN",
    device_profile: DeviceProfile = DeviceProfile.DESKTOP,
) -> GoogleSerpCapture:
    raw = RawEvidence(
        job_id=context.job_id,
        attempt_id=context.attempt_id,
        sha256=(key.encode().hex() + "0" * 64)[:64],
        storage_bucket="raw",
        object_key=f"google/{key}.gz",
        content_type="text/html",
        byte_length=100,
        captured_at=captured_at,
    )
    session.add(raw)
    session.flush()
    capture = GoogleSerpCapture(
        keyword_id=keyword.id,
        geo_code=geo_code,
        device_profile=device_profile,
        captured_at=captured_at,
        source_job_id=context.job_id,
        raw_evidence_id=raw.id,
        parser_version_id=context.parser_version_id,
        parser_version="google-serp-v1",
        ingestion_key=key,
        page_number=1,
        result_count=len(domains),
    )
    capture.results = [
        GoogleSerpResult(
            absolute_position=position,
            page_number=1,
            result_type="organic",
            title=f"Result {position}",
            url=f"https://{domain}/result-{position}",
            displayed_domain=domain,
        )
        for position, domain in enumerate(domains, start=1)
    ]
    session.add(capture)
    session.commit()
    return capture


def _client(factory: sessionmaker[Session]) -> TestClient:
    def override() -> Iterator[Session]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override
    return TestClient(app)


def test_google_domain_comparison_is_boundary_safe_deterministic_and_evidence_backed(
    engine: Engine,
) -> None:
    factory, keyword, context = _setup(engine)
    with factory() as session:
        capture = _add_google_capture(
            session,
            keyword=keyword,
            context=context,
            key="domain-comparison",
            captured_at=CAPTURED_AT,
            domains=[
                "shop.novel.example",
                "acme.example",
                "novel.example.attacker.com",
                "fakenovel.example",
                "other.example",
            ],
        )
    with _client(factory) as client:
        response = client.get(
            "/api/v1/rank-visibility/google-domain-comparison",
            params=[
                ("novel_domain", "WWW.NOVEL.EXAMPLE."),
                ("competitor_domain", "acme.example"),
            ],
        )
    app.dependency_overrides.clear()
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["source"] == "public_google_serp"
    assert body["novel"]["matched_organic_slots"] == 1
    assert body["novel"]["visibility_share_percent"] == 20.0
    assert body["novel"]["latest_rank"] == body["novel"]["best_rank"] == 1
    assert body["competitors"][0]["matched_organic_slots"] == 1
    assert body["comparisons"][0]["signals"] == ["visibility_tied"]
    assert body["evidence_capture_ids"] == [str(capture.id)]
    assert len(body["novel"]["result_ids"]) == 1
    assert not {"clicks", "impressions", "ctr", "average_position"} & body.keys()


def test_google_domain_comparison_uses_latest_capture_per_context(engine: Engine) -> None:
    factory, keyword, context = _setup(engine)
    with factory() as session:
        old = _add_google_capture(
            session,
            keyword=keyword,
            context=context,
            key="visibility-old",
            captured_at=CAPTURED_AT,
            domains=["novel.example", "novel.example"],
        )
        latest = _add_google_capture(
            session,
            keyword=keyword,
            context=context,
            key="visibility-latest",
            captured_at=CAPTURED_AT + timedelta(minutes=5),
            domains=["acme.example", "other.example"],
        )
        result = GoogleVisibilityService(session).domain_comparison(
            novel_domain="novel.example",
            competitor_domains=["acme.example"],
            keyword_id=None,
            geo_code=None,
            device_profile=None,
            from_at=None,
            to_at=None,
        )
    assert result.contexts_checked == 1
    assert result.evidence_capture_ids == [latest.id]
    assert old.id not in result.evidence_capture_ids
    assert result.novel.matched_organic_slots == 0
    assert result.competitors[0].matched_organic_slots == 1
    assert result.comparisons[0].signals == [
        "competitor_leads_visibility",
        "novel_missing_on_keyword",
    ]


def test_google_domain_comparison_multi_keyword_filters_and_missing_signals(
    engine: Engine,
) -> None:
    factory, first_keyword, context = _setup(engine)
    with factory() as session:
        second_keyword = Keyword(
            keyword_text="water wipes",
            normalized_text="water wipes",
            marketplace=Marketplace.AMAZON_IN,
            tier=TrackingTier.T1,
            tracking_status=KeywordTrackingStatus.ACTIVE,
            intent_cluster=IntentCluster.GENERIC_CATEGORY,
        )
        session.add(second_keyword)
        session.commit()
        _add_google_capture(
            session,
            keyword=first_keyword,
            context=context,
            key="multi-first",
            captured_at=CAPTURED_AT,
            domains=["novel.example"],
        )
        _add_google_capture(
            session,
            keyword=second_keyword,
            context=context,
            key="multi-second",
            captured_at=CAPTURED_AT + timedelta(minutes=1),
            domains=["acme.example"],
        )
        _add_google_capture(
            session,
            keyword=first_keyword,
            context=context,
            key="multi-other-geo",
            captured_at=CAPTURED_AT + timedelta(minutes=2),
            domains=["acme.example"],
            geo_code="US",
            device_profile=DeviceProfile.MOBILE,
        )
        result = GoogleVisibilityService(session).domain_comparison(
            novel_domain="novel.example",
            competitor_domains=["acme.example"],
            keyword_id=None,
            geo_code="IN",
            device_profile=DeviceProfile.DESKTOP,
            from_at=CAPTURED_AT - timedelta(seconds=1),
            to_at=CAPTURED_AT + timedelta(minutes=1, seconds=1),
        )
    assert result.contexts_checked == result.keyword_count == 2
    assert result.novel.keyword_coverage_count == 1
    assert result.competitors[0].keyword_coverage_count == 1
    assert result.comparisons[0].signals == [
        "visibility_tied",
        "novel_missing_on_keyword",
        "competitor_missing_on_keyword",
    ]


def test_google_domain_comparison_zero_results_and_malformed_domain(engine: Engine) -> None:
    factory, keyword, context = _setup(engine)
    with factory() as session:
        capture = _add_google_capture(
            session,
            keyword=keyword,
            context=context,
            key="zero-results",
            captured_at=CAPTURED_AT,
            domains=[],
        )
        result = GoogleVisibilityService(session).domain_comparison(
            novel_domain="novel.example",
            competitor_domains=["acme.example"],
            keyword_id=None,
            geo_code=None,
            device_profile=None,
            from_at=None,
            to_at=None,
        )
    assert result.evidence_capture_ids == [capture.id]
    assert result.novel.total_eligible_organic_slots == 0
    assert result.novel.visibility_share_percent == 0.0
    assert result.comparisons[0].signals == ["visibility_tied"]
    with _client(factory) as client:
        response = client.get(
            "/api/v1/rank-visibility/google-domain-comparison",
            params=[
                ("novel_domain", "https://novel.example"),
                ("competitor_domain", "acme.example"),
            ],
        )
    app.dependency_overrides.clear()
    assert response.status_code == 422
