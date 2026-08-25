import hashlib
import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from novel_signal.modules.collection.source_ingestion import (
    ensure_parser_version,
    persist_raw_source_page,
)
from novel_signal.modules.collection.storage import RawObjectStore
from novel_signal.parsers.amazon_ads import parse_report
from novel_signal.sources.base import RawSourcePage

from .models import (
    AdDaypartProfile,
    AdObservation,
    AdPresenceDaily,
    AmazonAdsSearchTermContribution,
    OwnAdPerformance,
    SpendEstimate,
)
from .schemas import (
    AdObservationCreate,
    AdSummaryRead,
    DaypartDerive,
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


def derive_dayparts(session: Session, data: DaypartDerive) -> list[AdDaypartProfile]:
    groups: dict[tuple[int, int], list[str]] = {}
    for slot in data.successful_captures:
        groups.setdefault((slot.weekday, slot.hour), []).append(slot.capture_id)
    observations = list(
        session.scalars(
            select(AdObservation).where(
                AdObservation.competitor_id == data.competitor_id,
                AdObservation.keyword_id == data.keyword_id,
                AdObservation.publication_status == "published",
                AdObservation.quarantine_reason.is_(None),
            )
        )
    )
    observed = {row.capture_id for row in observations if row.capture_id}
    results: list[AdDaypartProfile] = []
    for (weekday, hour), capture_ids in groups.items():
        item = session.scalar(
            select(AdDaypartProfile).where(
                AdDaypartProfile.competitor_id == data.competitor_id,
                AdDaypartProfile.keyword_id == data.keyword_id,
                AdDaypartProfile.weekday == weekday,
                AdDaypartProfile.hour == hour,
            )
        )
        values = {
            "presence_rate": len(observed.intersection(capture_ids)) / len(capture_ids),
            "sample_size": len(capture_ids),
            "status": "derived",
        }
        if item:
            for key, value in values.items():
                setattr(item, key, value)
        else:
            item = AdDaypartProfile(
                competitor_id=data.competitor_id,
                keyword_id=data.keyword_id,
                weekday=weekday,
                hour=hour,
                **values,
            )
            session.add(item)
        results.append(item)
    session.commit()
    for item in results:
        session.refresh(item)
    return results


def summarize_ads(session: Session, competitor_id: str) -> AdSummaryRead:
    presence = list(
        session.scalars(
            select(AdPresenceDaily).where(AdPresenceDaily.competitor_id == competitor_id)
        )
    )
    observations = list(
        session.scalars(
            select(AdObservation).where(
                AdObservation.competitor_id == competitor_id,
                AdObservation.publication_status == "published",
                AdObservation.quarantine_reason.is_(None),
            )
        )
    )
    positions = [row.sponsored_position for row in observations if row.sponsored_position]
    coverages = [row.coverage for row in presence if row.coverage is not None]
    return AdSummaryRead(
        competitor_id=competitor_id,
        continuous_ad_days=continuous_ad_days(presence),
        total_ad_days=len({row.day for row in presence if row.ad_days > 0}),
        keyword_breadth=len({row.keyword_id for row in presence if row.ad_days > 0}),
        average_slot_share=round(sum(coverages) / len(coverages), 3) if coverages else None,
        average_sponsored_position=round(sum(positions) / len(positions), 2) if positions else None,
        sample_size=len(observations),
    )


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


def ingest_stored_search_term_report(
    session: Session,
    *,
    object_store: RawObjectStore,
    job_id: uuid.UUID,
    attempt_id: uuid.UUID,
    page: RawSourcePage,
    profile_id: str,
    report_id: str,
    period_start: date,
    period_end: date,
    currency: str,
) -> list[AmazonAdsSearchTermContribution]:
    evidence = persist_raw_source_page(
        session,
        object_store=object_store,
        job_id=job_id,
        attempt_id=attempt_id,
        platform="amazon_ads_api",
        page=page,
    )
    parser = ensure_parser_version(
        session,
        platform="amazon_ads_api",
        page_type=page.resource_type,
        version="amazon-ads-search-term-v1",
    )
    return ingest_search_term_report(
        session,
        body=page.body,
        profile_id=profile_id,
        report_id=report_id,
        period_start=period_start,
        period_end=period_end,
        currency=currency,
        raw_capture_id=str(evidence.id),
        parse_run_id=str(parser.id),
    )
