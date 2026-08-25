from datetime import UTC, datetime

from novel_signal.db import Base
from novel_signal.modules.reviews.models import ReviewObservation, ReviewTopic
from novel_signal.modules.reviews.schemas import ReviewCreate
from novel_signal.modules.reviews.service import ingest_review, topic_summary
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def session() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[ReviewObservation.__table__, ReviewTopic.__table__])
    return Session(engine)


def review(fingerprint: str = "source-1") -> ReviewCreate:
    return ReviewCreate(
        target_id="product-1",
        platform="amazon.in",
        source="public_review",
        source_review_id="review-1",
        fingerprint=fingerprint,
        rating=2,
        title="Poor delivery",
        text="The package was late and caused irritation. contact me at test@example.com",
        captured_at=datetime.now(UTC),
        raw_capture_id="raw-1",
        parse_run_id="parser-v1",
    )


def test_review_fingerprint_is_idempotent_and_topics_are_deterministic() -> None:
    db = session()
    first = ingest_review(db, review())
    second = ingest_review(db, review())
    assert first.id == second.id
    assert db.query(ReviewObservation).count() == 1
    assert db.query(ReviewTopic).count() == 2
    assert "[redacted-email]" in (first.text or "")


def test_topic_summary_exposes_low_confidence_for_small_samples() -> None:
    db = session()
    ingest_review(db, review())
    summary = topic_summary(db, "product-1", None, None, None)
    assert summary
    assert all(item.confidence == "low" for item in summary)
    assert all(item.sample_size == 1 for item in summary)


def test_unpublished_reviews_do_not_reach_topic_metrics() -> None:
    db = session()
    ingest_review(
        db,
        review("source-2").model_copy(
            update={
                "source_review_id": "review-2",
                "publication_status": "quarantined",
                "quarantine_reason": "invalid evidence",
            }
        ),
    )
    assert topic_summary(db, "product-1", None, None, None) == []
