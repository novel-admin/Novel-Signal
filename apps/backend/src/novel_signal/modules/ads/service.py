from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AdObservation, AdPresenceDaily, OwnAdPerformance, SpendEstimate
from .schemas import AdObservationCreate, OwnPerformanceCreate, PresenceUpsert, SpendEstimateCreate


def record_observation(session: Session, data: AdObservationCreate) -> AdObservation:
    existing = session.scalar(
        select(AdObservation).where(AdObservation.fingerprint == data.fingerprint)
    )
    if existing:
        return existing
    item = AdObservation(**data.model_dump())
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


def upsert_presence(session: Session, data: PresenceUpsert) -> AdPresenceDaily:
    item = session.scalar(
        select(AdPresenceDaily).where(
            AdPresenceDaily.competitor_id == data.competitor_id,
            AdPresenceDaily.keyword_id == data.keyword_id,
            AdPresenceDaily.day == data.day,
        )
    )
    values = data.model_dump(exclude={"competitor_id", "keyword_id", "day"})
    values["coverage"] = (data.observed_slots / data.total_slots) if data.total_slots else None
    values["ad_days"] = 1 if data.observed_slots else 0
    if item:
        for key, value in values.items():
            setattr(item, key, value)
    else:
        item = AdPresenceDaily(
            competitor_id=data.competitor_id,
            keyword_id=data.keyword_id,
            day=data.day,
            **values,
        )
        session.add(item)
    session.commit()
    session.refresh(item)
    return item


def create_spend_estimate(session: Session, data: SpendEstimateCreate) -> SpendEstimate:
    if not (data.low <= data.expected <= data.high):
        raise ValueError("spend range must satisfy low <= expected <= high")
    item = SpendEstimate(**data.model_dump())
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


def record_own_performance(session: Session, data: OwnPerformanceCreate) -> OwnAdPerformance:
    item = OwnAdPerformance(**data.model_dump())
    session.add(item)
    session.commit()
    session.refresh(item)
    return item
