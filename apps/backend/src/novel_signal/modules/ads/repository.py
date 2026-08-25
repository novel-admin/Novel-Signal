from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    AdObservation,
    AdPresenceDaily,
    AmazonAdsSearchTermContribution,
    SpendEstimate,
)


def list_observations(
    session: Session, *, competitor_id: str | None, keyword_id: str | None, limit: int
) -> list[AdObservation]:
    query = select(AdObservation).order_by(AdObservation.captured_at.desc()).limit(limit)
    if competitor_id:
        query = query.where(AdObservation.competitor_id == competitor_id)
    if keyword_id:
        query = query.where(AdObservation.keyword_id == keyword_id)
    return list(session.scalars(query))


def list_presence(
    session: Session, *, competitor_id: str, keyword_id: str, limit: int
) -> list[AdPresenceDaily]:
    query = (
        select(AdPresenceDaily)
        .where(
            AdPresenceDaily.competitor_id == competitor_id, AdPresenceDaily.keyword_id == keyword_id
        )
        .order_by(AdPresenceDaily.day.desc())
        .limit(limit)
    )
    return list(session.scalars(query))


def list_estimates(session: Session, *, competitor_id: str, limit: int) -> list[SpendEstimate]:
    return list(
        session.scalars(
            select(SpendEstimate)
            .where(SpendEstimate.competitor_id == competitor_id)
            .order_by(SpendEstimate.period_end.desc())
            .limit(limit)
        )
    )


def list_search_term_contributions(
    session: Session, *, profile_id: str | None, limit: int
) -> list[AmazonAdsSearchTermContribution]:
    query = select(AmazonAdsSearchTermContribution).order_by(
        AmazonAdsSearchTermContribution.period_end.desc(),
        AmazonAdsSearchTermContribution.id,
    )
    if profile_id:
        query = query.where(AmazonAdsSearchTermContribution.profile_id == profile_id)
    return list(session.scalars(query.limit(limit)))
