import hashlib
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from novel_signal.parsers.amazon_ads import parse_report

from .models import (
    AdObservation,
    AdPresenceDaily,
    AmazonAdsSearchTermContribution,
    OwnAdPerformance,
    SpendEstimate,
)
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


def ingest_search_term_report(
    session: Session,
    *,
    body: bytes,
    profile_id: str,
    report_id: str,
    period_start: date,
    period_end: date,
    currency: str,
    raw_capture_id: str,
    parse_run_id: str,
) -> list[AmazonAdsSearchTermContribution]:
    stored: list[AmazonAdsSearchTermContribution] = []
    for row in parse_report(body):
        identity = "|".join(
            (
                profile_id,
                report_id,
                str(row["campaignId"]),
                str(row.get("adGroupId", "")),
                str(row["searchTerm"]).strip().lower(),
                period_start.isoformat(),
                period_end.isoformat(),
            )
        )
        fingerprint = hashlib.sha256(identity.encode()).hexdigest()
        existing = session.scalar(
            select(AmazonAdsSearchTermContribution).where(
                AmazonAdsSearchTermContribution.fingerprint == fingerprint
            )
        )
        if existing:
            stored.append(existing)
            continue
        contribution = AmazonAdsSearchTermContribution(
            profile_id=profile_id,
            campaign_id=str(row["campaignId"]),
            ad_group_id=str(row["adGroupId"]) if row.get("adGroupId") is not None else None,
            search_term=str(row["searchTerm"]),
            matched_keyword=str(row["keyword"]) if row.get("keyword") is not None else None,
            match_type=str(row["matchType"]) if row.get("matchType") is not None else None,
            period_start=period_start,
            period_end=period_end,
            impressions=int(row.get("impressions", 0)),
            clicks=int(row.get("clicks", 0)),
            spend=float(row.get("cost", row.get("spend", 0))),
            currency=currency,
            orders=int(row.get("purchases7d", row.get("orders", 0))),
            sales=float(row.get("sales7d", row.get("sales", 0))),
            raw_capture_id=raw_capture_id,
            parse_run_id=parse_run_id,
            report_id=report_id,
            fingerprint=fingerprint,
        )
        session.add(contribution)
        stored.append(contribution)
    session.commit()
    for item in stored:
        session.refresh(item)
    return stored
