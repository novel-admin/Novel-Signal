from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from novel_signal.db import Base
from novel_signal.modules.collection.amazon_product_publication import (
    AmazonProductPublicationConfig,
    AmazonProductPublisher,
)
from novel_signal.modules.collection.models import (
    CollectionAttempt,
    CollectionAttemptStatus,
    CollectionJob,
    CollectionJobStatus,
    CollectionJobType,
    CollectionSourceTier,
    ParserVersion,
    RawEvidence,
    RawEvidenceType,
)
from novel_signal.modules.collection.pipeline import PublishContext
from novel_signal.modules.listings.models import ListingChangeEvent, ListingSnapshot
from novel_signal.modules.price_monitoring.models import (
    PriceChangeEvent,
    PriceObservation,
    SellerOffer,
)
from novel_signal.modules.universe.models import (
    Competitor,
    CompetitorProduct,
    Marketplace,
    Product,
    TrackingTier,
)
from sqlalchemy import create_engine, delete, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

CAPTURED_AT = datetime(2026, 8, 30, tzinfo=UTC)


def _owned_harness() -> tuple[
    Any,
    sessionmaker[Session],
    PublishContext,
    AmazonProductPublicationConfig,
    dict[str, Any],
]:
    engine = create_engine("sqlite+pysqlite:///:memory:", poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def foreign_keys(connection: object, _: object) -> None:
        cursor = connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        product = Product(
            internal_sku="OWN-TEST",
            name="Wipes",
            brand="Novel",
            category="Care",
            marketplace=Marketplace.AMAZON_IN,
            marketplace_product_id="B0TEST0001",
            tracking_tier=TrackingTier.T1,
        )
        session.add(product)
        session.flush()
        job = CollectionJob(
            idempotency_key="publication-test",
            job_type=CollectionJobType.PRODUCT_DETAIL,
            source_tier=CollectionSourceTier.PUBLIC_PAGE,
            platform="amazon_in",
            product_id=product.id,
            scheduled_for=CAPTURED_AT,
            status=CollectionJobStatus.RUNNING,
        )
        session.add(job)
        session.flush()
        attempt = CollectionAttempt(
            job_id=job.id, attempt_number=1, status=CollectionAttemptStatus.RUNNING
        )
        session.add(attempt)
        session.flush()
        raw = RawEvidence(
            job_id=job.id,
            attempt_id=attempt.id,
            evidence_type=RawEvidenceType.RESPONSE_BODY,
            sha256="d" * 64,
            storage_bucket="raw",
            object_key="raw/d",
            content_type="text/html",
            byte_length=9,
            final_url="https://www.amazon.in/dp/B0TEST0001?token=not-persisted",
            capture_metadata={"requested_url": "https://www.amazon.in/dp/B0TEST0001#ignored"},
            captured_at=CAPTURED_AT,
        )
        parser = ParserVersion(
            platform="amazon_in", page_type="product_detail", version="amazon-product-v1"
        )
        session.add_all([raw, parser])
        session.commit()
        context = PublishContext(
            job_id=job.id,
            attempt_id=attempt.id,
            raw_evidence_id=raw.id,
            parser_version_id=parser.id,
            platform="amazon_in",
            page_type="product_detail",
            captured_at=CAPTURED_AT,
        )
        config = AmazonProductPublicationConfig(
            marketplace_product_id="B0TEST0001",
            geo_code="IN",
            device_profile="desktop",
            product_id=product.id,
        )
    return engine, factory, context, config, _record()


def _record() -> dict[str, Any]:
    return {
        "marketplace_product_id": "B0TEST0001",
        "title": "Novel Wipes",
        "brand": "Novel",
        "category_path": "Baby > Wipes",
        "description": "Gentle wipes",
        "bullets": ["Soft"],
        "key_features": ["Soft"],
        "a_plus_present": True,
        "a_plus_sections": [{"heading": "Why Novel"}],
        "image_urls": ["https://images.example/wipes.jpg"],
        "image_hashes": ["image-sha"],
        "image_count": 1,
        "video_present": True,
        "video_count": 1,
        "variation_count": 2,
        "variation_metadata": {"size": ["S", "M"]},
        "storefront_text": "Visit the Novel store",
        "availability_status": "available",
        "primary_price": Decimal("99"),
        "mrp": Decimal("120"),
        "discount_percent": Decimal("17.5"),
        "coupon_text": "Save ₹10",
        "coupon_value": Decimal("10"),
        "coupon_type": "absolute",
        "shipping_amount": Decimal("20"),
        "effective_price": Decimal("89"),
        "primary_seller_name": "Novel Store",
        "primary_seller_id": "NOVEL-1",
        "is_featured_offer": True,
        "seller_count": 1,
        "offers": [
            {
                "seller_name": "Novel Store",
                "seller_id": "NOVEL-1",
                "offer_price": Decimal("99"),
                "list_price": Decimal("120"),
                "shipping_amount": Decimal("20"),
                "coupon_value": Decimal("10"),
                "effective_price": Decimal("89"),
                "availability_status": "available",
                "is_featured_offer": True,
            }
        ],
        "content_metadata": {"pack_quantity": 1},
    }


def test_product_publication_creates_both_sinks_and_replays_idempotently() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def foreign_keys(connection: object, _: object) -> None:
        cursor = connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        product = Product(
            internal_sku="OWN-1",
            name="Wipes",
            brand="Novel",
            category="Care",
            marketplace=Marketplace.AMAZON_IN,
            marketplace_product_id="B0TEST0001",
            tracking_tier=TrackingTier.T1,
        )
        session.add(product)
        session.flush()
        job = CollectionJob(
            idempotency_key="product-publication",
            job_type=CollectionJobType.PRODUCT_DETAIL,
            source_tier=CollectionSourceTier.PUBLIC_PAGE,
            platform="amazon_in",
            product_id=product.id,
            scheduled_for=CAPTURED_AT,
            status=CollectionJobStatus.RUNNING,
        )
        session.add(job)
        session.flush()
        attempt = CollectionAttempt(
            job=job, attempt_number=1, status=CollectionAttemptStatus.RUNNING
        )
        session.add(attempt)
        session.flush()
        raw = RawEvidence(
            job_id=job.id,
            attempt_id=attempt.id,
            evidence_type=RawEvidenceType.RESPONSE_BODY,
            sha256="a" * 64,
            storage_bucket="raw",
            object_key="raw/a",
            content_type="text/html",
            byte_length=9,
            final_url="https://www.amazon.in/dp/B0TEST0001",
            capture_metadata={"requested_url": "https://www.amazon.in/dp/B0TEST0001"},
            captured_at=CAPTURED_AT,
        )
        parser = ParserVersion(
            platform="amazon_in", page_type="product_detail", version="amazon-product-v1"
        )
        session.add_all([raw, parser])
        session.commit()
        context = PublishContext(
            job_id=job.id,
            attempt_id=attempt.id,
            raw_evidence_id=raw.id,
            parser_version_id=parser.id,
            platform="amazon_in",
            page_type="product_detail",
            captured_at=CAPTURED_AT,
        )
        config = AmazonProductPublicationConfig(
            marketplace_product_id="B0TEST0001",
            geo_code="IN",
            device_profile="desktop",
            product_id=product.id,
        )
    record = {
        "marketplace_product_id": "B0TEST0001",
        "title": "Novel Wipes",
        "brand": "Novel",
        "category_path": "Baby > Wipes",
        "description": "Gentle wipes",
        "bullets": ["Soft"],
        "key_features": ["Soft"],
        "a_plus_present": True,
        "a_plus_sections": [{"heading": "Why Novel"}],
        "image_urls": ["https://images.example/wipes.jpg"],
        "image_hashes": ["image-sha"],
        "image_count": 1,
        "video_present": True,
        "video_count": 1,
        "variation_count": 2,
        "variation_metadata": {"size": ["S", "M"]},
        "storefront_text": "Visit the Novel store",
        "availability_status": "available",
        "primary_price": Decimal("99"),
        "mrp": Decimal("120"),
        "discount_percent": Decimal("17.5"),
        "coupon_text": "Save ₹10",
        "coupon_value": Decimal("10"),
        "coupon_type": "absolute",
        "shipping_amount": Decimal("20"),
        "effective_price": Decimal("89"),
        "primary_seller_name": "Novel Store",
        "primary_seller_id": "NOVEL-1",
        "is_featured_offer": True,
        "seller_count": 1,
        "offers": [
            {
                "seller_name": "Novel Store",
                "seller_id": "NOVEL-1",
                "offer_price": Decimal("99"),
                "list_price": Decimal("120"),
                "shipping_amount": Decimal("20"),
                "coupon_value": Decimal("10"),
                "effective_price": Decimal("89"),
                "availability_status": "available",
                "is_featured_offer": True,
            }
        ],
        "content_metadata": {"pack_quantity": 1},
    }
    publisher = AmazonProductPublisher(config=config, session_factory=factory)
    first = publisher.publish(context, (record,))
    replay = publisher.publish(context, (record,))
    with Session(engine) as session:
        raw2 = RawEvidence(
            job_id=context.job_id,
            attempt_id=context.attempt_id,
            evidence_type=RawEvidenceType.RESPONSE_BODY,
            sha256="c" * 64,
            storage_bucket="raw",
            object_key="raw/c",
            content_type="text/html",
            byte_length=10,
            final_url="https://www.amazon.in/dp/B0TEST0001?session=secret",
            captured_at=CAPTURED_AT + timedelta(minutes=1),
        )
        session.add(raw2)
        session.commit()
        second_context = PublishContext(
            job_id=context.job_id,
            attempt_id=context.attempt_id,
            raw_evidence_id=raw2.id,
            parser_version_id=context.parser_version_id,
            platform=context.platform,
            page_type=context.page_type,
            captured_at=raw2.captured_at,
        )
    second = publisher.publish(
        second_context,
        (dict(record, title="Novel Wipes Plus", primary_price=Decimal("109")),),
    )
    assert first["listing_publication"] == first["price_publication"] == "created"
    assert replay["listing_publication"] == replay["price_publication"] == "existing"
    assert first["listing_ingestion_key"] != first["price_ingestion_key"]
    assert first["listing_ingestion_key"] != second["listing_ingestion_key"]
    assert first["price_ingestion_key"] != second["price_ingestion_key"]
    with Session(engine) as session:
        listings = session.scalars(select(ListingSnapshot)).all()
        prices = session.scalars(select(PriceObservation)).all()
        assert len(listings) == len(prices) == 2
        assert len(session.scalars(select(SellerOffer)).all()) == 2
        assert any(
            change.field_name == "title"
            for change in session.scalars(select(ListingChangeEvent)).all()
        )
        assert any(
            event.new_price == Decimal("109.00")
            for event in session.scalars(select(PriceChangeEvent)).all()
        )
        listing = listings[0]
        price = prices[0]
        assert listing.product_id == price.product_id == config.product_id
        assert listing.title == "Novel Wipes"
        assert listing.a_plus_present is True
        assert listing.video_count == 1
        assert listing.variation_metadata == {"size": ["S", "M"]}
        assert price.primary_price == Decimal("99.00")
        assert price.effective_price == Decimal("89.00")
        assert price.primary_seller_id == "NOVEL-1"
        assert len(price.offers) == 1
        assert listing.content_metadata and listing.content_metadata["raw_evidence_id"] == str(
            context.raw_evidence_id
        )
        assert price.source_metadata and price.source_metadata["parser_version_id"] == str(
            context.parser_version_id
        )
        assert second_context.raw_evidence_id != context.raw_evidence_id
        assert "?" not in str(prices[1].source_url)
        assert "html" not in str(listing.content_metadata).lower()
        assert "html" not in str(price.source_metadata).lower()
    Base.metadata.drop_all(engine)


@pytest.mark.parametrize("records", [(), ({"marketplace_product_id": "B0TEST0001"},) * 2])
def test_product_publication_rejects_invalid_record_cardinality(
    records: tuple[dict[str, object], ...],
) -> None:
    publisher = AmazonProductPublisher(
        config=AmazonProductPublicationConfig(
            marketplace_product_id="B0TEST0001", geo_code=None, device_profile=None
        )
    )
    context = PublishContext(
        job_id=uuid4(),
        attempt_id=uuid4(),
        raw_evidence_id=uuid4(),
        parser_version_id=uuid4(),
        platform="amazon_in",
        page_type="product_detail",
        captured_at=CAPTURED_AT,
    )
    with pytest.raises(ValueError, match="exactly one record"):
        publisher.publish(context, records)  # type: ignore[arg-type]


def test_competitor_product_mapping_is_respected() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        competitor = Competitor(name="Acme")
        session.add(competitor)
        session.flush()
        competitor_product = CompetitorProduct(
            competitor_id=competitor.id,
            name="Acme Wipes",
            brand="Acme",
            category="Care",
            marketplace=Marketplace.AMAZON_IN,
            marketplace_product_id="B0TEST0002",
            tracking_tier=TrackingTier.T1,
        )
        session.add(competitor_product)
        session.flush()
        job = CollectionJob(
            idempotency_key="competitor-product-publication",
            job_type=CollectionJobType.PRODUCT_DETAIL,
            source_tier=CollectionSourceTier.PUBLIC_PAGE,
            platform="amazon_in",
            competitor_product_id=competitor_product.id,
            scheduled_for=CAPTURED_AT,
            status=CollectionJobStatus.RUNNING,
        )
        session.add(job)
        session.flush()
        attempt = CollectionAttempt(
            job_id=job.id, attempt_number=1, status=CollectionAttemptStatus.RUNNING
        )
        raw = RawEvidence(
            job_id=job.id,
            attempt=attempt,
            evidence_type=RawEvidenceType.RESPONSE_BODY,
            sha256="b" * 64,
            storage_bucket="raw",
            object_key="raw/b",
            content_type="text/html",
            byte_length=9,
            captured_at=CAPTURED_AT,
        )
        parser = ParserVersion(
            platform="amazon_in", page_type="product_detail", version="amazon-product-v1"
        )
        session.add_all([raw, parser])
        session.commit()
        context = PublishContext(
            job_id=job.id,
            attempt_id=attempt.id,
            raw_evidence_id=raw.id,
            parser_version_id=parser.id,
            platform="amazon_in",
            page_type="product_detail",
            captured_at=CAPTURED_AT,
        )
        config = AmazonProductPublicationConfig(
            marketplace_product_id="B0TEST0002",
            geo_code=None,
            device_profile=None,
            competitor_product_id=competitor_product.id,
        )
    result = AmazonProductPublisher(config=config, session_factory=factory).publish(
        context,
        ({"marketplace_product_id": "B0TEST0002"},),
    )
    assert result["listing_publication"] == "created"
    with Session(engine) as session:
        assert (
            session.scalars(select(ListingSnapshot)).one().competitor_product_id
            == config.competitor_product_id
        )
        assert (
            session.scalars(select(PriceObservation)).one().competitor_product_id
            == config.competitor_product_id
        )
    Base.metadata.drop_all(engine)


def test_partial_publication_recovery_reuses_the_existing_sink() -> None:
    for missing in ("price", "listing"):
        engine, factory, context, config, record = _owned_harness()
        publisher = AmazonProductPublisher(config=config, session_factory=factory)
        publisher.publish(context, (record,))
        with Session(engine) as session:
            if missing == "price":
                session.execute(delete(SellerOffer))
                session.execute(delete(PriceObservation))
            else:
                session.execute(delete(ListingChangeEvent))
                session.execute(delete(ListingSnapshot))
            session.commit()
        recovered = publisher.publish(context, (record,))
        assert recovered[f"{missing}_publication"] == "created"
        assert (
            recovered[f"{'listing' if missing == 'price' else 'price'}_publication"] == "existing"
        )
        with Session(engine) as session:
            assert len(session.scalars(select(ListingSnapshot)).all()) == 1
            assert len(session.scalars(select(PriceObservation)).all()) == 1
            assert len(session.scalars(select(SellerOffer)).all()) == 1
            assert len(session.scalars(select(ListingChangeEvent)).all()) == 0
            assert len(session.scalars(select(PriceChangeEvent)).all()) == 0
        Base.metadata.drop_all(engine)


def test_existing_ingestion_key_rejects_materially_different_replay_data() -> None:
    engine, factory, context, config, record = _owned_harness()
    publisher = AmazonProductPublisher(config=config, session_factory=factory)
    publisher.publish(context, (record,))
    with pytest.raises(ValueError, match="conflicts with existing ingestion identity"):
        publisher.publish(context, (dict(record, title="Changed title"),))
    changed_price = dict(record, primary_price=Decimal("109"))
    with pytest.raises(ValueError, match="conflicts with existing ingestion identity"):
        publisher.publish(context, (changed_price,))
    with Session(engine) as session:
        assert len(session.scalars(select(ListingSnapshot)).all()) == 1
        assert len(session.scalars(select(PriceObservation)).all()) == 1
        assert session.scalars(select(ListingSnapshot)).one().title == "Novel Wipes"
        assert session.scalars(select(PriceObservation)).one().primary_price == Decimal("99.00")
    Base.metadata.drop_all(engine)


@pytest.mark.parametrize(
    "failure", ["asin", "raw", "parser", "job", "attempt", "product", "competitor"]
)
def test_lineage_and_identity_failures_publish_nothing(failure: str) -> None:
    engine, factory, context, config, record = _owned_harness()
    if failure == "asin":
        record = dict(record, marketplace_product_id="B0TEST0009")
    elif failure == "raw":
        context = PublishContext(**{**context.__dict__, "raw_evidence_id": uuid4()})
    elif failure == "parser":
        context = PublishContext(**{**context.__dict__, "parser_version_id": uuid4()})
    elif failure == "job":
        context = PublishContext(**{**context.__dict__, "job_id": uuid4()})
    elif failure == "attempt":
        context = PublishContext(**{**context.__dict__, "attempt_id": uuid4()})
    elif failure == "product":
        config = AmazonProductPublicationConfig(
            marketplace_product_id=config.marketplace_product_id,
            geo_code=config.geo_code,
            device_profile=config.device_profile,
            product_id=uuid4(),
        )
    else:
        config = AmazonProductPublicationConfig(
            marketplace_product_id=config.marketplace_product_id,
            geo_code=config.geo_code,
            device_profile=config.device_profile,
            competitor_product_id=uuid4(),
        )
    with pytest.raises(ValueError):
        AmazonProductPublisher(config=config, session_factory=factory).publish(context, (record,))
    with Session(engine) as session:
        assert session.scalars(select(ListingSnapshot)).all() == []
        assert session.scalars(select(PriceObservation)).all() == []
    Base.metadata.drop_all(engine)
