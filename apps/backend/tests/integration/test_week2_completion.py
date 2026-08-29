from __future__ import annotations

from datetime import UTC, datetime, timedelta

from novel_signal.db import Base
from novel_signal.modules.actions.models import ChangeEvent
from novel_signal.modules.collection.models import (
    CollectionAttempt,
    CollectionAttemptStatus,
    CollectionJob,
    CollectionJobStatus,
    CollectionJobType,
    CollectionSourceTier,
    ParserVersion,
    RawEvidence,
)
from novel_signal.modules.collection.pipeline import PublishContext
from novel_signal.modules.keywords.models import (
    Keyword,
    KeywordSourceType,
    KeywordTrackingStatus,
)
from novel_signal.modules.keywords.publication import (
    KeywordEvidencePublisher,
    KeywordPublicationConfig,
)
from novel_signal.modules.listings.schemas import SnapshotIn
from novel_signal.modules.listings.service import ListingService
from novel_signal.modules.price_monitoring.models import AvailabilityStatus
from novel_signal.modules.price_monitoring.schemas import PriceObservationIn
from novel_signal.modules.price_monitoring.service import PriceService
from novel_signal.modules.universe.models import Marketplace, Product, TrackingTier
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


def test_week2_offline_completion_acceptance() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def sqlite_config(connection: object, _: object) -> None:
        connection.create_function(  # type: ignore[attr-defined]
            "btrim", 1, lambda value: value.strip(), deterministic=True
        )
        cursor = connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    now = datetime(2026, 8, 27, 10, tzinfo=UTC)
    with Session(engine, expire_on_commit=False) as session:
        product = Product(
            internal_sku="W2-OWN-1",
            name="Novel Baby Wipes",
            brand="Novel",
            category="Baby Wipes",
            marketplace=Marketplace.AMAZON_IN,
            marketplace_product_id="B0W2ACCEPT",
            tracking_tier=TrackingTier.T1,
        )
        seed = Keyword(
            keyword_text="acceptance seed",
            normalized_text="acceptance seed",
            marketplace=Marketplace.AMAZON_IN,
            tier=TrackingTier.T3,
            tracking_status=KeywordTrackingStatus.ACTIVE,
        )
        session.add_all((product, seed))
        session.flush()
        job = CollectionJob(
            idempotency_key="w2-acceptance-keyword",
            job_type=CollectionJobType.SERP,
            source_tier=CollectionSourceTier.FIRST_PARTY_API,
            platform="amazon_in",
            keyword_id=seed.id,
            status=CollectionJobStatus.RUNNING,
            scheduled_for=now,
            attempt_count=1,
        )
        attempt = CollectionAttempt(
            job=job,
            attempt_number=1,
            status=CollectionAttemptStatus.RUNNING,
            started_at=now,
        )
        parser = ParserVersion(platform="amazon_in", page_type="keyword", version="acceptance-v1")
        session.add_all((job, attempt, parser))
        session.flush()
        raw = RawEvidence(
            job_id=job.id,
            attempt_id=attempt.id,
            sha256="a" * 64,
            storage_bucket="test",
            object_key="acceptance/raw",
            content_type="application/json",
            byte_length=2,
            captured_at=now,
        )
        session.add(raw)
        session.commit()

        context = PublishContext(
            job_id=job.id,
            attempt_id=attempt.id,
            raw_evidence_id=raw.id,
            parser_version_id=parser.id,
            platform="amazon_in",
            page_type="keyword",
            captured_at=now,
        )

    record = ({"keyword_text": "Novel Baby Wipes", "observation_metadata": {"rank": 1}},)
    for source in (KeywordSourceType.BRAND_ANALYTICS, KeywordSourceType.SEARCH_CONSOLE):
        publisher = KeywordEvidencePublisher(
            config=KeywordPublicationConfig(
                marketplace=Marketplace.AMAZON_IN,
                source_type=source,
                default_tier=TrackingTier.T3,
                default_tracking_status=KeywordTrackingStatus.ACTIVE,
            ),
            session_factory=factory,
        )
        publisher.publish(context, record)
    # A retry keeps both the keyword identity and source lineage idempotent.
    KeywordEvidencePublisher(
        config=KeywordPublicationConfig(
            marketplace=Marketplace.AMAZON_IN,
            source_type=KeywordSourceType.BRAND_ANALYTICS,
            default_tier=TrackingTier.T3,
            default_tracking_status=KeywordTrackingStatus.ACTIVE,
        ),
        session_factory=factory,
    ).publish(context, record)

    with Session(engine, expire_on_commit=False) as session:
        keyword = session.scalars(
            select(Keyword).where(Keyword.normalized_text == "novel baby wipes")
        ).one()
        assert keyword.intent_cluster.value == "own_brand"
        assert len(keyword.sources) == 2
        assert all(
            str(raw.id) == source.source_metadata["raw_evidence_id"]  # type: ignore[index]
            for source in keyword.sources
        )
        assert all(
            str(parser.id) == source.source_metadata["parser_version_id"]  # type: ignore[index]
            for source in keyword.sources
        )

        listing = ListingService(session)
        listing.ingest(
            SnapshotIn(
                marketplace_product_id="B0W2ACCEPT",
                captured_at=now,
                ingestion_key="listing-baseline",
                title="Novel Baby Wipes",
            )
        )
        listing.ingest(
            SnapshotIn(
                marketplace_product_id="B0W2ACCEPT",
                captured_at=now + timedelta(minutes=1),
                ingestion_key="listing-change",
                title="Novel Baby Wipes Plus",
            )
        )
        price = PriceService(session)
        price.ingest(
            PriceObservationIn(
                marketplace_product_id="B0W2ACCEPT",
                observed_at=now,
                ingestion_key="price-baseline",
                primary_price="500",
                availability_status=AvailabilityStatus.AVAILABLE,
            )
        )
        price.ingest(
            PriceObservationIn(
                marketplace_product_id="B0W2ACCEPT",
                observed_at=now + timedelta(minutes=2),
                ingestion_key="price-change",
                primary_price="450",
                availability_status=AvailabilityStatus.AVAILABLE,
            )
        )
        price.ingest(
            PriceObservationIn(
                marketplace_product_id="B0W2ACCEPT",
                observed_at=now + timedelta(minutes=3),
                ingestion_key="availability-change",
                availability_status=AvailabilityStatus.UNAVAILABLE,
            )
        )
        events = session.scalars(select(ChangeEvent)).all()
        assert {"listing_modified", "price_price_decrease", "price_became_unavailable"} <= {
            event.event_type for event in events
        }
        assert all(event.old_observation_id and event.new_observation_id for event in events)

    Base.metadata.drop_all(engine)
    engine.dispose()
