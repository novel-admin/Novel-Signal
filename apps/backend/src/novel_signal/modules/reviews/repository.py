from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import ReviewObservation, ReviewTopicTrend


def list_reviews(
    session: Session,
    *,
    target_id: str | None,
    platform: str | None,
    limit: int,
    cursor: str | None,
) -> list[ReviewObservation]:
    query = select(ReviewObservation).order_by(
        ReviewObservation.captured_at.desc(), ReviewObservation.id.desc()
    ).limit(limit + 1)
    if target_id:
        query = query.where(ReviewObservation.target_id == target_id)
    if platform:
        query = query.where(ReviewObservation.platform == platform)
    if cursor:
        query = query.where(ReviewObservation.id < cursor)
    return list(session.scalars(query))


def list_trends(
    session: Session, target_id: str | None, start: date | None, end: date | None
) -> list[ReviewTopicTrend]:
    query = select(ReviewTopicTrend).order_by(
        ReviewTopicTrend.period_start.asc(), ReviewTopicTrend.topic.asc()
    )
    if target_id:
        query = query.where(ReviewTopicTrend.target_id == target_id)
    if start:
        query = query.where(ReviewTopicTrend.period_start >= start)
    if end:
        query = query.where(ReviewTopicTrend.period_start <= end)
    return list(session.scalars(query))

