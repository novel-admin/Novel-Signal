from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AdObservation, AdPresenceDaily, OwnAdPerformance, SpendEstimate
from .schemas import (
    AdObservationCreate,
    OwnPerformanceCreate,
    PresenceDerive,
    PresenceUpsert,
    SpendEstimateCreate,
)


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


def derive_presence(session: Session, data: PresenceDerive) -> AdPresenceDaily:
    successful = set(data.successful_capture_ids)
    rows = list(
        session.scalars(
            select(AdObservation).where(
                AdObservation.competitor_id == data.competitor_id,
                AdObservation.keyword_id == data.keyword_id,
                AdObservation.publication_status == "published",
                AdObservation.raw_capture_id.is_not(None),
                AdObservation.parse_run_id.is_not(None),
                AdObservation.quarantine_reason.is_(None),
            )
        )
    )
    observed = {
        row.capture_id
        for row in rows
        if row.capture_id and row.capture_id in successful and row.captured_at.date() == data.day
    }
    return upsert_presence(
        session,
        PresenceUpsert(
            competitor_id=data.competitor_id,
            keyword_id=data.keyword_id,
            day=data.day,
            observed_slots=len(observed),
            total_slots=len(successful),
            confidence=len(successful) / max(len(successful), 24),
            evidence_ref=",".join(sorted(observed)) or None,
        ),
    )


def continuous_ad_days(rows: list[AdPresenceDaily]) -> int:
    active_days = sorted({row.day for row in rows if row.ad_days > 0}, reverse=True)
    if not active_days:
        return 0
    streak = 1
    for newer, older in zip(active_days, active_days[1:], strict=False):
        if (newer - older).days != 1:
            break
        streak += 1
    return streak


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
