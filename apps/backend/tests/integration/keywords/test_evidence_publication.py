from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from novel_signal.collectors.base import CaptureRequest, CaptureResult
from novel_signal.db import Base
from novel_signal.modules.collection.execution import CollectionExecutionError
from novel_signal.modules.collection.models import (
    CollectionAttempt,
    CollectionAttemptStatus,
    CollectionJob,
    CollectionJobStatus,
    CollectionJobType,
    CollectionSourceTier,
    RawEvidence,
)
from novel_signal.modules.collection.parsing import EnvelopeValidator, ParserRegistry
from novel_signal.modules.collection.pipeline import EvidencePipeline
from novel_signal.modules.collection.source_evidence import SourceRawEvidenceBridge
from novel_signal.modules.collection.storage import StoredRawObject
from novel_signal.modules.keywords.models import (
    IntentCluster,
    Keyword,
    KeywordSource,
    KeywordSourceType,
    KeywordTrackingStatus,
)
from novel_signal.modules.keywords.publication import (
    KeywordEvidencePublisher,
    KeywordPublicationConfig,
)
from novel_signal.modules.universe.models import Marketplace, TrackingTier
from novel_signal.parsers.base import ParsedEnvelope
from novel_signal.parsers.brand_analytics_keywords import BrandAnalyticsSearchQueryPerformanceParser
from novel_signal.parsers.search_console_keywords import GoogleSearchConsoleKeywordParser
from novel_signal.sources.base import RawSourcePage, SourceType, SyncRequest
from sqlalchemy import Engine, create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

CAPTURED_AT = datetime(2026, 8, 25, 9, 0, tzinfo=UTC)


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
    def put_raw(self, *, platform: str, page_type: str, body: bytes) -> StoredRawObject:
        digest = hashlib.sha256(body).hexdigest()
        return StoredRawObject(
            sha256=digest,
            bucket="test-raw",
            object_key=f"raw/{platform}/{page_type}/{digest}.gz",
            byte_length=len(body),
            compressed_byte_length=max(1, len(body) // 2),
        )


class OnePageAdapter:
    source_type = SourceType.AMAZON_BRAND_ANALYTICS

    def __init__(self, page: RawSourcePage) -> None:
        self.page = page

    async def verify_connection(self) -> None:
        return None

    async def fetch(self, request: SyncRequest) -> tuple[RawSourcePage, ...]:
        return (self.page,)


def keyword_publisher(
    engine: Engine,
    source_type: KeywordSourceType,
) -> KeywordEvidencePublisher:
    return KeywordEvidencePublisher(
        config=KeywordPublicationConfig(
            marketplace=Marketplace.AMAZON_IN,
            source_type=source_type,
            default_tier=TrackingTier.T3,
            default_tracking_status=KeywordTrackingStatus.ACTIVE,
            default_intent_cluster=IntentCluster.UNCLASSIFIED,
        ),
        session_factory=sessionmaker(bind=engine, expire_on_commit=False),
    )


def pipeline(engine: Engine, parser: object) -> EvidencePipeline:
    registry = ParserRegistry()
    registry.register(parser)  # type: ignore[arg-type]
    return EvidencePipeline(
        parser_registry=registry,
        object_store=MemoryStore(),
        session_factory=sessionmaker(bind=engine, expire_on_commit=False),
    )


def running_job(session: Session, *, platform: str) -> tuple[CollectionJob, CollectionAttempt]:
    keyword = Keyword(
        keyword_text=f"collection seed {uuid.uuid4()}",
        normalized_text=f"collection seed {uuid.uuid4()}",
        marketplace=Marketplace.AMAZON_IN,
        tier=TrackingTier.T3,
        tracking_status=KeywordTrackingStatus.ACTIVE,
        intent_cluster=IntentCluster.UNCLASSIFIED,
    )
    session.add(keyword)
    session.flush()
    job = CollectionJob(
        idempotency_key=f"keyword-publication:{keyword.id}",
        job_type=CollectionJobType.SERP,
        source_tier=CollectionSourceTier.FIRST_PARTY_API,
        platform=platform,
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


def brand_analytics_body(query: str = "Sensitive Baby Wipes") -> bytes:
    """Sanitized fixture shaped after Amazon's published SQP report schema."""
    return json.dumps(
        {
            "reportSpecification": {
                "reportType": "GET_BRAND_ANALYTICS_SEARCH_QUERY_PERFORMANCE_REPORT",
                "reportOptions": {"reportPeriod": "WEEK", "asin": "B0TESTASIN"},
                "dataStartTime": "2026-08-17",
                "dataEndTime": "2026-08-23",
                "marketplaceIds": ["A21TJRUUN4KGV"],
            },
            "dataByAsin": [
                {
                    "startDate": "2026-08-17",
                    "endDate": "2026-08-23",
                    "asin": "B0TESTASIN",
                    "searchQueryData": {
                        "searchQuery": query,
                        "searchQueryScore": 7,
                        "searchQueryVolume": 1200,
                    },
                    "impressionData": {
                        "totalQueryImpressionCount": 10000,
                        "asinImpressionCount": 765,
                        "asinImpressionShare": 0.0765,
                    },
                    "clickData": {
                        "totalClickCount": 1000,
                        "totalClickRate": 0.1,
                        "asinClickCount": 50,
                        "asinClickShare": 0.05,
                    },
                    "cartAddData": {
                        "totalCartAddCount": 200,
                        "totalCartAddRate": 0.02,
                        "asinCartAddCount": 10,
                        "asinCartAddShare": 0.05,
                    },
                    "purchaseData": {
                        "totalPurchaseCount": 100,
                        "totalPurchaseRate": 0.01,
                        "asinPurchaseCount": 5,
                        "asinPurchaseShare": 0.05,
                    },
                }
            ]
        }
    ).encode()


def gsc_body(query: str = "Sensitive Baby Wipes") -> bytes:
    return json.dumps(
        {
            "rows": [
                {
                    "keys": [
                        query,
                        "https://noveltissues.com/wipes",
                        "IND",
                        "MOBILE",
                        "2026-08-24",
                    ],
                    "clicks": 11,
                    "impressions": 90,
                    "ctr": 0.1222,
                    "position": 4.5,
                }
            ]
        }
    ).encode()


def process_raw(
    *,
    engine: Engine,
    parser: object,
    source_type: KeywordSourceType,
    body: bytes,
) -> dict[str, Any]:
    evidence_pipeline = pipeline(engine, parser)
    with Session(engine, expire_on_commit=False) as session:
        job, attempt = running_job(session, platform=parser.platform)  # type: ignore[attr-defined]
    result = evidence_pipeline.process(
        job_id=job.id,
        attempt_id=attempt.id,
        platform=parser.platform,  # type: ignore[attr-defined]
        request=CaptureRequest(
            url="https://source.test/raw",
            target_id="source-target",
            page_type=parser.page_type,  # type: ignore[attr-defined]
        ),
        capture=CaptureResult(
            final_url="https://source.test/raw",
            body=body,
            content_type="application/json",
        ),
        validator=EnvelopeValidator(required_fields=("keyword_text", "observation_metadata")),
        publisher=keyword_publisher(engine, source_type),
        captured_at=CAPTURED_AT,
    )
    assert result.quarantine is None
    return {
        "job": job,
        "attempt": attempt,
        "pipeline": evidence_pipeline,
        "result": result,
    }


def test_brand_analytics_parser_extracts_supported_query_metrics() -> None:
    envelope = BrandAnalyticsSearchQueryPerformanceParser().parse(brand_analytics_body())

    assert envelope.records == (
        {
            "keyword_text": "Sensitive Baby Wipes",
            "observation_metadata": {
                "report_period": "WEEK",
                "report_asins": "B0TESTASIN",
                "report_start_date": "2026-08-17",
                "report_end_date": "2026-08-23",
                "marketplace_ids": ["A21TJRUUN4KGV"],
                "asin": "B0TESTASIN",
                "start_date": "2026-08-17",
                "end_date": "2026-08-23",
                "search_query_score": 7,
                "search_query_volume": 1200,
                "total_query_impression_count": 10000,
                "asin_impression_count": 765,
                "asin_impression_share": 0.0765,
                "total_click_count": 1000,
                "total_click_rate": 0.1,
                "asin_click_count": 50,
                "asin_click_share": 0.05,
                "total_cart_add_count": 200,
                "total_cart_add_rate": 0.02,
                "asin_cart_add_count": 10,
                "asin_cart_add_share": 0.05,
                "total_purchase_count": 100,
                "total_purchase_rate": 0.01,
                "asin_purchase_count": 5,
                "asin_purchase_share": 0.05,
            },
        },
    )
    blank = BrandAnalyticsSearchQueryPerformanceParser().parse(brand_analytics_body("  "))
    assert blank.records == ()
    assert blank.warnings
    with pytest.raises(ValueError, match="reportSpecification"):
        BrandAnalyticsSearchQueryPerformanceParser().parse(b'{"dataByAsin": []}')


def test_gsc_parser_extracts_query_metrics_and_skips_blank_queries() -> None:
    parser = GoogleSearchConsoleKeywordParser(
        dimensions=("query", "page", "country", "device", "date")
    )
    envelope = parser.parse(gsc_body())

    assert envelope.records[0]["keyword_text"] == "Sensitive Baby Wipes"
    assert envelope.records[0]["observation_metadata"] == {
        "dimensions": {
            "query": "Sensitive Baby Wipes",
            "page": "https://noveltissues.com/wipes",
            "country": "IND",
            "device": "MOBILE",
            "date": "2026-08-24",
        },
        "clicks": 11,
        "impressions": 90,
        "ctr": 0.1222,
        "position": 4.5,
    }
    assert parser.parse(gsc_body(" ")).records == ()
    with pytest.raises(ValueError, match="rows must be a list"):
        parser.parse(b'{"rows": {}}')


def test_brand_analytics_publication_retains_exact_s12_lineage(engine: Engine) -> None:
    parser = BrandAnalyticsSearchQueryPerformanceParser()
    processed = process_raw(
        engine=engine,
        parser=parser,
        source_type=KeywordSourceType.BRAND_ANALYTICS,
        body=brand_analytics_body(),
    )
    result = processed["result"]

    with Session(engine) as session:
        keyword = session.scalars(
            select(Keyword).where(Keyword.normalized_text == "sensitive baby wipes")
        ).one()
        source = keyword.sources[0]
        assert source.source_type is KeywordSourceType.BRAND_ANALYTICS
        assert source.source_metadata is not None
        assert source.source_metadata["raw_evidence_id"] == result.metadata["raw_evidence_id"]
        assert source.source_metadata["parser_version_id"] == result.metadata["parser_version_id"]
        assert source.source_metadata["resource_type"] == parser.page_type
        assert source.source_metadata["source_type"] == "brand_analytics"
        assert source.source_metadata["observation"]["search_query_score"] == 7  # type: ignore[index]
        assert len(source.source_reference) <= 500
        assert str(result.metadata["raw_evidence_id"]) in source.source_reference
        assert str(result.metadata["parser_version_id"]) in source.source_reference
        assert brand_analytics_body().decode() not in json.dumps(source.source_metadata)


@pytest.mark.asyncio
async def test_t4_evidence_metadata_flows_into_keyword_provenance(engine: Engine) -> None:
    parser = BrandAnalyticsSearchQueryPerformanceParser()
    body = brand_analytics_body()
    with Session(engine, expire_on_commit=False) as session:
        job, attempt = running_job(session, platform=parser.platform)
    bridge = SourceRawEvidenceBridge(
        adapter=OnePageAdapter(
            RawSourcePage(
                source=SourceType.AMAZON_BRAND_ANALYTICS,
                resource_type=parser.page_type,
                body=body,
                content_type="application/json",
                request_fingerprint="ba-request-fingerprint",
            )
        ),
        object_store=MemoryStore(),
        session_factory=sessionmaker(bind=engine, expire_on_commit=False),
    )
    bridge_result = await bridge.execute(
        job_id=job.id,
        attempt_id=attempt.id,
        request=SyncRequest(
            resource_type=parser.page_type,
            window_start=CAPTURED_AT,
            window_end=CAPTURED_AT,
        ),
        captured_at=CAPTURED_AT,
    )
    result = pipeline(engine, parser).process_persisted_raw(
        job_id=job.id,
        attempt_id=attempt.id,
        raw_evidence_id=uuid.UUID(bridge_result.metadata["raw_evidence_id"]),
        platform=parser.platform,
        page_type=parser.page_type,
        body=body,
        validator=EnvelopeValidator(required_fields=("keyword_text", "observation_metadata")),
        publisher=keyword_publisher(engine, KeywordSourceType.BRAND_ANALYTICS),
    )
    with Session(engine) as session:
        keyword = session.scalars(
            select(Keyword).where(Keyword.normalized_text == "sensitive baby wipes")
        ).one()
        source = keyword.sources[0]
        assert source.source_metadata is not None
        assert source.source_metadata["raw_evidence_id"] == result.metadata["raw_evidence_id"]
        assert source.source_metadata["request_fingerprint"] == "ba-request-fingerprint"
        assert source.source_metadata["raw_source_type"] == "amazon_brand_analytics"


def test_replay_is_idempotent_and_different_evidence_is_distinct(engine: Engine) -> None:
    parser = BrandAnalyticsSearchQueryPerformanceParser()
    processed = process_raw(
        engine=engine,
        parser=parser,
        source_type=KeywordSourceType.BRAND_ANALYTICS,
        body=brand_analytics_body(),
    )
    result = processed["result"]
    replay = processed["pipeline"].process_persisted_raw(
        job_id=processed["job"].id,
        attempt_id=processed["attempt"].id,
        raw_evidence_id=uuid.UUID(result.metadata["raw_evidence_id"]),
        platform=parser.platform,
        page_type=parser.page_type,
        body=brand_analytics_body(),
        validator=EnvelopeValidator(required_fields=("keyword_text", "observation_metadata")),
        publisher=keyword_publisher(engine, KeywordSourceType.BRAND_ANALYTICS),
    )
    assert replay.metadata["created_keywords"] == 0
    assert replay.metadata["published_keyword_sources"] == 0

    with Session(engine) as session:
        first_reference = session.scalars(
            select(KeywordSource.source_reference).where(
                KeywordSource.source_type == KeywordSourceType.BRAND_ANALYTICS
            )
        ).one()

    process_raw(
        engine=engine,
        parser=parser,
        source_type=KeywordSourceType.BRAND_ANALYTICS,
        body=brand_analytics_body("  sensitive   baby wipes  "),
    )
    with Session(engine) as session:
        keyword = session.scalars(
            select(Keyword).where(Keyword.normalized_text == "sensitive baby wipes")
        ).one()
        sources = [
            source
            for source in keyword.sources
            if source.source_type is KeywordSourceType.BRAND_ANALYTICS
        ]
        assert len(sources) == 2
        assert first_reference in {source.source_reference for source in sources}
        assert sources[0].source_reference != sources[1].source_reference
        assert len(
            session.scalars(
                select(Keyword).where(Keyword.normalized_text == "sensitive baby wipes")
            ).all()
        ) == 1


def test_curated_keyword_fields_are_preserved_and_sources_coexist(engine: Engine) -> None:
    with Session(engine) as session:
        curated = Keyword(
            keyword_text="Sensitive Baby Wipes",
            normalized_text="sensitive baby wipes",
            marketplace=Marketplace.AMAZON_IN,
            category="Baby Care",
            tier=TrackingTier.T1,
            tracking_status=KeywordTrackingStatus.PAUSED,
            intent_cluster=IntentCluster.PROBLEM_BENEFIT,
            notes="curated by category team",
            sources=[
                KeywordSource(
                    source_type=KeywordSourceType.MANUAL,
                    source_reference="manual:seed",
                )
            ],
        )
        session.add(curated)
        session.commit()

    process_raw(
        engine=engine,
        parser=BrandAnalyticsSearchQueryPerformanceParser(),
        source_type=KeywordSourceType.BRAND_ANALYTICS,
        body=brand_analytics_body(),
    )
    process_raw(
        engine=engine,
        parser=GoogleSearchConsoleKeywordParser(
            dimensions=("query", "page", "country", "device", "date")
        ),
        source_type=KeywordSourceType.SEARCH_CONSOLE,
        body=gsc_body(),
    )
    with Session(engine) as session:
        keyword = session.scalars(
            select(Keyword).where(Keyword.normalized_text == "sensitive baby wipes")
        ).one()
        assert keyword.category == "Baby Care"
        assert keyword.tier is TrackingTier.T1
        assert keyword.tracking_status is KeywordTrackingStatus.PAUSED
        assert keyword.intent_cluster is IntentCluster.PROBLEM_BENEFIT
        assert keyword.notes == "curated by category team"
        assert {source.source_type for source in keyword.sources} == {
            KeywordSourceType.MANUAL,
            KeywordSourceType.BRAND_ANALYTICS,
            KeywordSourceType.SEARCH_CONSOLE,
        }
        gsc_source = next(
            source
            for source in keyword.sources
            if source.source_type is KeywordSourceType.SEARCH_CONSOLE
        )
        assert gsc_source.source_metadata is not None
        assert gsc_source.source_metadata["observation"]["clicks"] == 11  # type: ignore[index]


def test_blank_source_rows_do_not_create_keyword_provenance(engine: Engine) -> None:
    parser = GoogleSearchConsoleKeywordParser(dimensions=("query",))
    evidence_pipeline = pipeline(engine, parser)
    with Session(engine, expire_on_commit=False) as session:
        job, attempt = running_job(session, platform=parser.platform)
    result = evidence_pipeline.process(
        job_id=job.id,
        attempt_id=attempt.id,
        platform=parser.platform,
        request=CaptureRequest(
            url="https://source.test/raw",
            target_id="source",
            page_type=parser.page_type,
        ),
        capture=CaptureResult(
            final_url="https://source.test/raw",
            body=gsc_body(" "),
            content_type="application/json",
        ),
        validator=EnvelopeValidator(
            required_fields=("keyword_text", "observation_metadata"),
            minimum_rows=0,
        ),
        publisher=keyword_publisher(engine, KeywordSourceType.SEARCH_CONSOLE),
    )
    assert result.quarantine is None
    assert result.metadata["published_keyword_sources"] == 0
    with Session(engine) as session:
        assert session.query(KeywordSource).count() == 0


def test_invalid_envelope_never_publishes_and_raw_evidence_remains(engine: Engine) -> None:
    class InvalidKeywordParser:
        platform = "amazon_brand_analytics"
        page_type = "brand_analytics_search_query_performance"
        version = "invalid-keyword-parser-v1"

        def parse(self, raw: bytes) -> ParsedEnvelope:
            return ParsedEnvelope(
                parser_version=self.version,
                page_type=self.page_type,
                records=({"observation_metadata": {}},),
            )

    parser = InvalidKeywordParser()
    evidence_pipeline = pipeline(engine, parser)
    with Session(engine, expire_on_commit=False) as session:
        job, attempt = running_job(session, platform=parser.platform)
    result = evidence_pipeline.process(
        job_id=job.id,
        attempt_id=attempt.id,
        platform=parser.platform,
        request=CaptureRequest(
            url="https://source.test/raw",
            target_id="source",
            page_type=parser.page_type,
        ),
        capture=CaptureResult(
            final_url="https://source.test/raw",
            body=b"{}",
            content_type="application/json",
        ),
        validator=EnvelopeValidator(required_fields=("keyword_text", "observation_metadata")),
        publisher=keyword_publisher(engine, KeywordSourceType.BRAND_ANALYTICS),
    )
    assert result.quarantine is not None
    with Session(engine) as session:
        assert session.query(RawEvidence).count() == 1
        assert session.query(KeywordSource).count() == 0


def test_publisher_failure_keeps_immutable_raw_evidence(engine: Engine) -> None:
    class FailingPublisher:
        def publish(
            self,
            context: object,
            records: tuple[dict[str, Any], ...],
        ) -> dict[str, Any]:
            raise RuntimeError("downstream publication failed")

    parser = BrandAnalyticsSearchQueryPerformanceParser()
    evidence_pipeline = pipeline(engine, parser)
    with Session(engine, expire_on_commit=False) as session:
        job, attempt = running_job(session, platform=parser.platform)
    with pytest.raises(RuntimeError, match="downstream publication failed"):
        evidence_pipeline.process(
            job_id=job.id,
            attempt_id=attempt.id,
            platform=parser.platform,
            request=CaptureRequest(
                url="https://source.test/raw",
                target_id="source",
                page_type=parser.page_type,
            ),
            capture=CaptureResult(
                final_url="https://source.test/raw",
                body=brand_analytics_body(),
                content_type="application/json",
            ),
            validator=EnvelopeValidator(required_fields=("keyword_text", "observation_metadata")),
            publisher=FailingPublisher(),
        )
    with Session(engine) as session:
        assert session.query(RawEvidence).count() == 1
        assert session.query(KeywordSource).count() == 0


def test_persisted_raw_body_mismatch_cannot_publish_under_wrong_lineage(engine: Engine) -> None:
    parser = BrandAnalyticsSearchQueryPerformanceParser()
    processed = process_raw(
        engine=engine,
        parser=parser,
        source_type=KeywordSourceType.BRAND_ANALYTICS,
        body=brand_analytics_body(),
    )

    with pytest.raises(CollectionExecutionError) as error:
        processed["pipeline"].process_persisted_raw(
            job_id=processed["job"].id,
            attempt_id=processed["attempt"].id,
            raw_evidence_id=uuid.UUID(processed["result"].metadata["raw_evidence_id"]),
            platform=parser.platform,
            page_type=parser.page_type,
            body=brand_analytics_body("different body"),
            validator=EnvelopeValidator(
                required_fields=("keyword_text", "observation_metadata")
            ),
            publisher=keyword_publisher(engine, KeywordSourceType.BRAND_ANALYTICS),
        )
    assert error.value.code == "raw_evidence_body_mismatch"

    with Session(engine) as session:
        assert session.query(RawEvidence).count() == 1
        assert session.query(KeywordSource).count() == 1
