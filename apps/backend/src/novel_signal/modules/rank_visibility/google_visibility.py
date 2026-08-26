"""Persistence and read services for normalized Google organic visibility."""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Self
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import Select, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from novel_signal.modules.keywords.models import Keyword
from novel_signal.modules.rank_visibility.errors import (
    RankVisibilityConflictError,
    RankVisibilityNotFoundError,
    RankVisibilityValidationError,
)
from novel_signal.modules.rank_visibility.models import (
    DeviceProfile,
    GoogleSerpCapture,
    GoogleSerpResult,
)


class GoogleSerpResultIn(BaseModel):
    absolute_position: int = Field(gt=0)
    page_number: int = Field(gt=0)
    result_type: str = Field(min_length=1, max_length=50)
    title: str = Field(min_length=1, max_length=1000)
    url: str = Field(min_length=1, max_length=2048)
    displayed_domain: str = Field(min_length=1, max_length=255)
    snippet: str | None = Field(default=None, max_length=2000)
    identity_match: str | None = None
    identity_domain: str | None = Field(default=None, max_length=255)
    result_metadata: dict[str, object] | None = None
    query: str | None = Field(default=None, max_length=500, exclude=True)

    @field_validator("result_type")
    @classmethod
    def organic_only(cls, value: str) -> str:
        if value.strip().lower() != "organic":
            raise ValueError("Google visibility accepts organic results only")
        return "organic"

    @field_validator("title", "displayed_domain")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Google result text must not be blank")
        return normalized

    @field_validator("identity_match")
    @classmethod
    def known_identity(cls, value: str | None) -> str | None:
        if value not in {None, "novel", "competitor"}:
            raise ValueError("Google result identity is invalid")
        return value

    @field_validator("url")
    @classmethod
    def safe_public_url(cls, value: str) -> str:
        parsed = urlsplit(value.strip())
        try:
            port = parsed.port
        except ValueError:
            raise ValueError("Google result URL is invalid") from None
        del port
        if (
            parsed.scheme.lower() not in {"http", "https"}
            or parsed.hostname is None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
            or any(character.isspace() for character in parsed.hostname)
            or any(ord(character) < 32 for character in value)
        ):
            raise ValueError("Google result URL must be a safe public destination")
        return value.strip()

    @model_validator(mode="after")
    def metadata_is_compact(self) -> Self:
        if _contains_raw_payload(self.result_metadata):
            raise ValueError("Google result metadata must not contain raw HTML or bodies")
        return self


class GoogleCaptureIngest(BaseModel):
    keyword_id: uuid.UUID
    geo_code: str = Field(min_length=1, max_length=50)
    device_profile: DeviceProfile
    captured_at: datetime
    source_job_id: uuid.UUID
    raw_evidence_id: uuid.UUID
    parser_version_id: uuid.UUID
    parser_version: str = Field(min_length=1, max_length=100)
    ingestion_key: str = Field(min_length=1, max_length=255)
    page_number: int = Field(gt=0)
    capture_metadata: dict[str, object] | None = None
    results: list[GoogleSerpResultIn] = Field(min_length=1)

    @field_validator("geo_code", "parser_version", "ingestion_key")
    @classmethod
    def strip_required(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Google capture value must not be blank")
        return normalized

    @model_validator(mode="after")
    def consistent_records(self) -> Self:
        positions = [row.absolute_position for row in self.results]
        if len(positions) != len(set(positions)):
            raise ValueError("Google result positions must be unique")
        if any(row.page_number != self.page_number for row in self.results):
            raise ValueError("Google result page number must match its capture")
        if _contains_raw_payload(self.capture_metadata):
            raise ValueError("Google capture metadata must not contain raw HTML or bodies")
        return self


class GoogleDomainVisibility(BaseModel):
    domain: str
    matched_organic_slots: int
    total_eligible_organic_slots: int
    visibility_share_percent: float
    keyword_coverage_count: int
    latest_rank: int | None
    best_rank: int | None
    capture_ids: list[uuid.UUID]
    result_ids: list[uuid.UUID]


class GoogleDomainComparisonRow(BaseModel):
    competitor_domain: str
    slot_count_difference: int
    keyword_coverage_difference: int
    signals: list[str]


class GoogleDomainComparison(BaseModel):
    source: str = "public_google_serp"
    contexts_checked: int
    keyword_count: int
    novel: GoogleDomainVisibility
    competitors: list[GoogleDomainVisibility]
    comparisons: list[GoogleDomainComparisonRow]
    evidence_capture_ids: list[uuid.UUID]


class GoogleVisibilityRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def by_ingestion_key(self, key: str) -> GoogleSerpCapture | None:
        return self.session.scalar(
            select(GoogleSerpCapture)
            .where(GoogleSerpCapture.ingestion_key == key)
            .options(selectinload(GoogleSerpCapture.results))
        )

    def capture(self, capture_id: uuid.UUID) -> GoogleSerpCapture | None:
        return self.session.scalar(
            select(GoogleSerpCapture)
            .where(GoogleSerpCapture.id == capture_id)
            .options(selectinload(GoogleSerpCapture.results))
        )

    def history(
        self,
        *,
        keyword_id: uuid.UUID,
        domain: str | None = None,
        geo_code: str | None = None,
        device_profile: DeviceProfile | None = None,
        from_at: datetime | None = None,
        to_at: datetime | None = None,
    ) -> list[tuple[GoogleSerpResult, GoogleSerpCapture]]:
        statement: Select[tuple[GoogleSerpResult, GoogleSerpCapture]] = select(
            GoogleSerpResult, GoogleSerpCapture
        ).join(GoogleSerpCapture)
        conditions = [GoogleSerpCapture.keyword_id == keyword_id]
        if domain:
            normalized = domain.strip().lower().strip(".")
            conditions.append(
                or_(
                    GoogleSerpResult.displayed_domain == normalized,
                    GoogleSerpResult.identity_domain == normalized,
                )
            )
        if geo_code:
            conditions.append(GoogleSerpCapture.geo_code == geo_code)
        if device_profile:
            conditions.append(GoogleSerpCapture.device_profile == device_profile)
        if from_at:
            conditions.append(GoogleSerpCapture.captured_at >= from_at)
        if to_at:
            conditions.append(GoogleSerpCapture.captured_at <= to_at)
        return [
            (result, capture)
            for result, capture in self.session.execute(
                statement.where(*conditions).order_by(
                    GoogleSerpCapture.captured_at, GoogleSerpResult.absolute_position
                )
            ).all()
        ]

    def current_captures(
        self,
        *,
        keyword_id: uuid.UUID | None = None,
        geo_code: str | None = None,
        device_profile: DeviceProfile | None = None,
        from_at: datetime | None = None,
        to_at: datetime | None = None,
    ) -> list[GoogleSerpCapture]:
        statement = select(GoogleSerpCapture).options(selectinload(GoogleSerpCapture.results))
        if keyword_id:
            statement = statement.where(GoogleSerpCapture.keyword_id == keyword_id)
        if geo_code:
            statement = statement.where(GoogleSerpCapture.geo_code == geo_code)
        if device_profile:
            statement = statement.where(GoogleSerpCapture.device_profile == device_profile)
        if from_at:
            statement = statement.where(GoogleSerpCapture.captured_at >= from_at)
        if to_at:
            statement = statement.where(GoogleSerpCapture.captured_at <= to_at)
        captures = list(
            self.session.scalars(
                statement.order_by(GoogleSerpCapture.captured_at, GoogleSerpCapture.id)
            ).unique()
        )
        # Current visibility uses only the latest capture for each independent context.
        latest: dict[tuple[uuid.UUID, str, DeviceProfile], GoogleSerpCapture] = {}
        for capture in captures:
            latest[(capture.keyword_id, capture.geo_code, capture.device_profile)] = capture
        return sorted(latest.values(), key=lambda item: (item.captured_at, str(item.id)))


class GoogleVisibilityService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = GoogleVisibilityRepository(session)

    def ingest(self, payload: GoogleCaptureIngest) -> GoogleSerpCapture:
        if self.session.get(Keyword, payload.keyword_id) is None:
            raise RankVisibilityNotFoundError("Google visibility keyword was not found")
        capture = GoogleSerpCapture(
            keyword_id=payload.keyword_id,
            geo_code=payload.geo_code,
            device_profile=payload.device_profile,
            captured_at=payload.captured_at,
            source_job_id=payload.source_job_id,
            raw_evidence_id=payload.raw_evidence_id,
            parser_version_id=payload.parser_version_id,
            parser_version=payload.parser_version,
            ingestion_key=payload.ingestion_key,
            page_number=payload.page_number,
            result_count=len(payload.results),
            capture_metadata=payload.capture_metadata,
        )
        capture.results = [
            GoogleSerpResult(
                absolute_position=row.absolute_position,
                page_number=row.page_number,
                result_type=row.result_type,
                title=row.title,
                url=row.url,
                displayed_domain=row.displayed_domain,
                snippet=row.snippet,
                identity_match=row.identity_match,
                identity_domain=row.identity_domain,
                result_metadata=row.result_metadata,
            )
            for row in payload.results
        ]
        self.session.add(capture)
        try:
            self.session.commit()
        except IntegrityError as error:
            self.session.rollback()
            raise RankVisibilityConflictError(
                "Google visibility ingestion identity already exists"
            ) from error
        return self.get_capture(capture.id)

    def get_capture(self, capture_id: uuid.UUID) -> GoogleSerpCapture:
        capture = self.repository.capture(capture_id)
        if capture is None:
            raise RankVisibilityNotFoundError("Google visibility capture was not found")
        return capture

    def history(self, **filters: object) -> list[tuple[GoogleSerpResult, GoogleSerpCapture]]:
        return self.repository.history(**filters)  # type: ignore[arg-type]

    def latest_rank(self, **filters: object) -> GoogleSerpResult | None:
        rows = self.history(**filters)
        if not rows:
            return None
        latest_at = rows[-1][1].captured_at
        return min(
            (result for result, capture in rows if capture.captured_at == latest_at),
            key=lambda result: result.absolute_position,
        )

    def domain_comparison(
        self,
        *,
        novel_domain: str,
        competitor_domains: list[str],
        keyword_id: uuid.UUID | None,
        geo_code: str | None,
        device_profile: DeviceProfile | None,
        from_at: datetime | None,
        to_at: datetime | None,
    ) -> GoogleDomainComparison:
        novel = normalize_domain(novel_domain)
        competitors = [normalize_domain(value) for value in competitor_domains]
        if not competitors:
            raise RankVisibilityValidationError("Provide at least one competitor domain")
        if len(set(competitors)) != len(competitors) or novel in competitors:
            raise RankVisibilityValidationError("Google comparison domains must be distinct")
        captures = self.repository.current_captures(
            keyword_id=keyword_id,
            geo_code=geo_code,
            device_profile=device_profile,
            from_at=from_at,
            to_at=to_at,
        )
        total = sum(len(capture.results) for capture in captures)

        def visibility(domain: str) -> GoogleDomainVisibility:
            matches = [
                (result, capture)
                for capture in captures
                for result in capture.results
                if domain_matches(result.displayed_domain, domain)
            ]
            latest_rank = None
            if matches:
                latest_at = max(capture.captured_at for _, capture in matches)
                latest_rank = min(
                    result.absolute_position
                    for result, capture in matches
                    if capture.captured_at == latest_at
                )
            return GoogleDomainVisibility(
                domain=domain,
                matched_organic_slots=len(matches),
                total_eligible_organic_slots=total,
                visibility_share_percent=round(len(matches) / total * 100, 2) if total else 0.0,
                keyword_coverage_count=len(_matched_keywords(captures, domain)),
                latest_rank=latest_rank,
                best_rank=min((result.absolute_position for result, _ in matches), default=None),
                capture_ids=sorted({capture.id for _, capture in matches}, key=str),
                result_ids=sorted((result.id for result, _ in matches), key=str),
            )

        novel_visibility = visibility(novel)
        competitor_visibility = [visibility(domain) for domain in competitors]
        novel_keywords = _matched_keywords(captures, novel)
        comparisons = []
        for item in competitor_visibility:
            signals = []
            if novel_visibility.matched_organic_slots > item.matched_organic_slots:
                signals.append("novel_leads_visibility")
            elif novel_visibility.matched_organic_slots < item.matched_organic_slots:
                signals.append("competitor_leads_visibility")
            else:
                signals.append("visibility_tied")
            competitor_keywords = _matched_keywords(captures, item.domain)
            if competitor_keywords - novel_keywords:
                signals.append("novel_missing_on_keyword")
            if novel_keywords - competitor_keywords:
                signals.append("competitor_missing_on_keyword")
            comparisons.append(
                GoogleDomainComparisonRow(
                    competitor_domain=item.domain,
                    slot_count_difference=(
                        novel_visibility.matched_organic_slots - item.matched_organic_slots
                    ),
                    keyword_coverage_difference=(
                        novel_visibility.keyword_coverage_count - item.keyword_coverage_count
                    ),
                    signals=signals,
                )
            )
        return GoogleDomainComparison(
            contexts_checked=len(captures),
            keyword_count=len({capture.keyword_id for capture in captures}),
            novel=novel_visibility,
            competitors=competitor_visibility,
            comparisons=comparisons,
            evidence_capture_ids=sorted((capture.id for capture in captures), key=str),
        )


_DOMAIN = re.compile(
    r"(?=.{1,253}\.?$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?\.?"
)


def normalize_domain(value: str) -> str:
    normalized = value.strip().lower().strip(".")
    if normalized.startswith("www."):
        normalized = normalized[4:]
    if not _DOMAIN.fullmatch(normalized):
        raise RankVisibilityValidationError("Google comparison domain is malformed")
    return normalized


def domain_matches(observed: str, configured: str) -> bool:
    normalized = observed.strip().lower().strip(".")
    if normalized.startswith("www."):
        normalized = normalized[4:]
    return normalized == configured or normalized.endswith(f".{configured}")


def _matched_keywords(captures: list[GoogleSerpCapture], domain: str) -> set[uuid.UUID]:
    return {
        capture.keyword_id
        for capture in captures
        if any(domain_matches(result.displayed_domain, domain) for result in capture.results)
    }


def _contains_raw_payload(value: object) -> bool:
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = str(key).strip().lower()
            if normalized in {"body", "html", "raw_body", "raw_html", "response_body"}:
                return True
            if _contains_raw_payload(nested):
                return True
    elif isinstance(value, list):
        return any(_contains_raw_payload(item) for item in value)
    return isinstance(value, str) and "<html" in value.lower()
