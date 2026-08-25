from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import ReviewObservation, ReviewTopic, ReviewTopicTrend
from .repository import list_trends
from .schemas import ReviewCreate, ReviewMetrics, TopicSummary

TOPIC_RULES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("leakage", "complaint", ("leak", "leaking", "spill")),
    ("fit", "complaint", ("fit", "size", "tight", "loose")),
    ("fragrance", "neutral", ("fragrance", "smell", "scent", "odor")),
    ("irritation", "complaint", ("irritat", "rash", "itch", "burn")),
    ("delivery", "complaint", ("delivery", "deliver", "shipping", "late")),
    ("value", "praise", ("value", "worth", "quality", "recommend")),
)


def _topics(text: str | None) -> list[tuple[str, str]]:
    lowered = (text or "").lower()
    return [
        (topic, kind)
        for topic, kind, words in TOPIC_RULES
        if any(word in lowered for word in words)
    ]


def _confidence(sample_size: int) -> str:
    return "high" if sample_size >= 30 else "medium" if sample_size >= 10 else "low"


def ingest_review(session: Session, data: ReviewCreate) -> ReviewObservation:
    existing = session.scalar(
        select(ReviewObservation).where(ReviewObservation.fingerprint == data.fingerprint)
    )
    if existing:
        return existing
    values = data.model_dump()
    row = ReviewObservation(**values, topic_type=None, confidence="low")
    topics = _topics(data.text)
    if topics:
        row.topic_type = topics[0][1]
    session.add(row)
    try:
        session.flush()
        for topic, kind in topics:
            session.add(ReviewTopic(review_id=row.id, topic=topic, topic_type=kind))
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = session.scalar(
            select(ReviewObservation).where(ReviewObservation.fingerprint == data.fingerprint)
        )
        if existing:
            return existing
        raise
    session.refresh(row)
    return row


def topic_summary(
    session: Session,
    target_id: str | None,
    topic_type: str | None,
    start: date | None,
    end: date | None,
) -> list[TopicSummary]:
    query = (
        select(
            ReviewTopic.topic,
            ReviewTopic.topic_type,
            func.count(ReviewTopic.id),
            func.avg(ReviewObservation.rating),
        )
        .join(ReviewObservation, ReviewObservation.id == ReviewTopic.review_id)
        .where(
            ReviewObservation.publication_status == "published",
            ReviewObservation.raw_capture_id.is_not(None),
            ReviewObservation.parse_run_id.is_not(None),
            ReviewObservation.quarantine_reason.is_(None),
        )
        .group_by(ReviewTopic.topic, ReviewTopic.topic_type)
        .order_by(ReviewTopic.topic)
    )
    if target_id:
        query = query.where(ReviewObservation.target_id == target_id)
    if topic_type:
        query = query.where(ReviewTopic.topic_type == topic_type)
    if start:
        query = query.where(ReviewObservation.published_on >= start)
    if end:
        query = query.where(ReviewObservation.published_on <= end)
    return [
        TopicSummary(
            topic=topic,
            topic_type=kind,
            review_count=int(count),
            average_rating=round(float(avg), 2) if avg is not None else None,
            sample_size=int(count),
            confidence=_confidence(int(count)),
        )
        for topic, kind, count, avg in session.execute(query)
    ]


def trends(
    session: Session, target_id: str | None, start: date | None, end: date | None
) -> list[ReviewTopicTrend]:
    # Materialize deterministic weekly aggregates; repeated requests update the same unique rows.
    query = select(ReviewObservation).where(
        ReviewObservation.published_on.is_not(None),
        ReviewObservation.publication_status == "published",
        ReviewObservation.raw_capture_id.is_not(None),
        ReviewObservation.parse_run_id.is_not(None),
        ReviewObservation.quarantine_reason.is_(None),
    )
    if target_id:
        query = query.where(ReviewObservation.target_id == target_id)
    if start:
        query = query.where(ReviewObservation.published_on >= start)
    if end:
        query = query.where(ReviewObservation.published_on <= end)
    rows = list(session.scalars(query))
    groups: dict[tuple[str, date, str, str], list[ReviewObservation]] = defaultdict(list)
    for row in rows:
        if row.published_on is None:
            continue
        published_on = row.published_on
        assert isinstance(published_on, date)
        week = published_on - timedelta(days=published_on.weekday())
        for topic, kind in _topics(row.text):
            groups[(row.target_id, week, topic, kind)].append(row)
    for (row_target, week, topic, kind), values in groups.items():
        existing = session.scalar(
            select(ReviewTopicTrend).where(
                ReviewTopicTrend.target_id == row_target,
                ReviewTopicTrend.period_start == week,
                ReviewTopicTrend.topic == topic,
            )
        )
        if existing:
            existing.review_count = len(values)
            existing.average_rating = sum(v.rating for v in values) / len(values)
            existing.sample_size = len(values)
            existing.confidence = _confidence(len(values))
        else:
            session.add(
                ReviewTopicTrend(
                    target_id=row_target,
                    period_start=week,
                    topic=topic,
                    topic_type=kind,
                    review_count=len(values),
                    average_rating=sum(v.rating for v in values) / len(values),
                    sample_size=len(values),
                    confidence=_confidence(len(values)),
                )
            )
    session.commit()
    return list_trends(session, target_id, start, end)


def review_metrics(
    session: Session, target_id: str, start: date | None, end: date | None
) -> ReviewMetrics:
    query = select(ReviewObservation).where(
        ReviewObservation.target_id == target_id,
        ReviewObservation.publication_status == "published",
        ReviewObservation.raw_capture_id.is_not(None),
        ReviewObservation.parse_run_id.is_not(None),
        ReviewObservation.quarantine_reason.is_(None),
        ReviewObservation.published_on.is_not(None),
    )
    if start:
        query = query.where(ReviewObservation.published_on >= start)
    if end:
        query = query.where(ReviewObservation.published_on <= end)
    rows = sorted(session.scalars(query), key=lambda row: row.published_on or date.min)
    if not rows:
        return ReviewMetrics(
            target_id=target_id,
            review_count=0,
            average_rating=None,
            review_velocity_per_day=None,
            rating_change=None,
            period_start=start,
            period_end=end,
            sample_size=0,
            confidence="low",
        )
    first_day = rows[0].published_on
    last_day = rows[-1].published_on
    assert first_day is not None and last_day is not None
    days = max((last_day - first_day).days + 1, 1)
    split = max(len(rows) // 2, 1)
    early = rows[:split]
    late = rows[split:] or rows[-1:]
    early_rating = sum(row.rating for row in early) / len(early)
    late_rating = sum(row.rating for row in late) / len(late)
    return ReviewMetrics(
        target_id=target_id,
        review_count=len(rows),
        average_rating=round(sum(row.rating for row in rows) / len(rows), 2),
        review_velocity_per_day=round(len(rows) / days, 3),
        rating_change=round(late_rating - early_rating, 2),
        period_start=first_day,
        period_end=last_day,
        sample_size=len(rows),
        confidence=_confidence(len(rows)),
    )
