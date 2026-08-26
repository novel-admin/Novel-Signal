"""Publish validated Google organic SERP records into S3 visibility history."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from novel_signal.db import SessionLocal
from novel_signal.modules.collection.models import CollectionJob, ParserVersion, RawEvidence
from novel_signal.modules.collection.pipeline import PublishContext
from novel_signal.modules.rank_visibility.errors import RankVisibilityConflictError
from novel_signal.modules.rank_visibility.google_visibility import (
    GoogleCaptureIngest,
    GoogleSerpResultIn,
    GoogleVisibilityService,
)
from novel_signal.modules.rank_visibility.models import DeviceProfile, GoogleSerpCapture


@dataclass(frozen=True)
class GoogleSerpPublicationConfig:
    keyword_id: UUID
    geo_code: str
    device_profile: DeviceProfile
    query: str
    page_number: int = 1
    profile_id: str | None = None

    def __post_init__(self) -> None:
        if not self.geo_code.strip() or not self.query.strip():
            raise ValueError("Google SERP publication requires geo code and query")
        if self.page_number < 1:
            raise ValueError("Google SERP publication page number must be positive")


class GoogleSerpPublisher:
    def __init__(
        self,
        *,
        config: GoogleSerpPublicationConfig,
        session_factory: sessionmaker[Session] = SessionLocal,
    ) -> None:
        self.config = config
        self.session_factory = session_factory

    def publish(
        self,
        context: PublishContext,
        records: tuple[dict[str, Any], ...],
    ) -> dict[str, Any]:
        if not records:
            raise ValueError("Google SERP publication requires at least one result")
        if context.platform != "google" or context.page_type != "serp":
            raise ValueError("Google SERP publication context is invalid")

        parsed = [GoogleSerpResultIn.model_validate(record) for record in records]
        expected_query = _normalized_query(self.config.query)
        if any(
            row.query is not None and _normalized_query(row.query) != expected_query
            for row in parsed
        ):
            raise ValueError("Google SERP parsed query does not match the configured keyword")

        with self.session_factory() as session:
            raw_evidence = session.get(RawEvidence, context.raw_evidence_id)
            parser_version = session.get(ParserVersion, context.parser_version_id)
            job = session.get(CollectionJob, context.job_id)
            if raw_evidence is None:
                raise ValueError("Google SERP raw evidence is unavailable")
            if parser_version is None:
                raise ValueError("Google SERP parser version is unavailable")
            if job is None:
                raise ValueError("Google SERP source job is unavailable")
            if (
                raw_evidence.job_id != context.job_id
                or raw_evidence.attempt_id != context.attempt_id
                or job.keyword_id != self.config.keyword_id
            ):
                raise ValueError("Google SERP publication lineage does not match its source")
            if (
                parser_version.platform != "google"
                or parser_version.page_type != "serp"
                or parser_version.version != "google-serp-v1"
            ):
                raise ValueError("Google SERP parser lineage is invalid")

            ingestion_key = _ingestion_key(context=context, config=self.config)
            payload = GoogleCaptureIngest(
                keyword_id=self.config.keyword_id,
                geo_code=self.config.geo_code,
                device_profile=self.config.device_profile,
                captured_at=context.captured_at,
                source_job_id=context.job_id,
                raw_evidence_id=context.raw_evidence_id,
                parser_version_id=context.parser_version_id,
                parser_version=parser_version.version,
                ingestion_key=ingestion_key,
                page_number=self.config.page_number,
                capture_metadata=_capture_metadata(context=context, config=self.config),
                results=parsed,
            )
            service = GoogleVisibilityService(session)
            existing = service.repository.by_ingestion_key(ingestion_key)
            if existing is not None:
                if not _same_publication(existing, payload):
                    raise RankVisibilityConflictError(
                        "Google visibility replay conflicts with its stored observation"
                    )
                return _metadata(existing, ingestion_key, "existing")

            capture = service.ingest(payload)
            return _metadata(capture, ingestion_key, "created")


def _ingestion_key(*, context: PublishContext, config: GoogleSerpPublicationConfig) -> str:
    canonical = {
        "device_profile": config.device_profile.value,
        "geo_code": config.geo_code.strip(),
        "keyword_id": str(config.keyword_id),
        "page_number": config.page_number,
        "parser_version_id": str(context.parser_version_id),
        "raw_evidence_id": str(context.raw_evidence_id),
    }
    digest = hashlib.sha256(
        json.dumps(canonical, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()
    return f"google-serp:{digest}"


def _capture_metadata(
    *, context: PublishContext, config: GoogleSerpPublicationConfig
) -> dict[str, object]:
    metadata: dict[str, object] = {
        "raw_evidence_id": str(context.raw_evidence_id),
        "parser_version_id": str(context.parser_version_id),
        "attempt_id": str(context.attempt_id),
        "platform": "google",
        "page_type": "serp",
        "query": config.query.strip(),
        "query_source": "configured_keyword",
        "page_number": config.page_number,
    }
    if config.profile_id:
        metadata["profile_id"] = config.profile_id
    return metadata


def _same_publication(capture: GoogleSerpCapture, payload: GoogleCaptureIngest) -> bool:
    if (
        capture.keyword_id != payload.keyword_id
        or capture.geo_code != payload.geo_code
        or capture.device_profile != payload.device_profile
        or capture.raw_evidence_id != payload.raw_evidence_id
        or capture.parser_version_id != payload.parser_version_id
        or capture.page_number != payload.page_number
        or capture.capture_metadata != payload.capture_metadata
        or len(capture.results) != len(payload.results)
    ):
        return False
    persisted = [
        (
            row.absolute_position,
            row.page_number,
            row.result_type,
            row.title,
            row.url,
            row.displayed_domain,
            row.snippet,
            row.identity_match,
            row.identity_domain,
            row.result_metadata,
        )
        for row in capture.results
    ]
    incoming = [
        (
            row.absolute_position,
            row.page_number,
            row.result_type,
            row.title,
            row.url,
            row.displayed_domain,
            row.snippet,
            row.identity_match,
            row.identity_domain,
            row.result_metadata,
        )
        for row in payload.results
    ]
    return persisted == incoming


def _metadata(capture: GoogleSerpCapture, ingestion_key: str, publication: str) -> dict[str, Any]:
    return {
        "capture_id": str(capture.id),
        "ingestion_key": ingestion_key,
        "published_records": capture.result_count,
        "publication": publication,
    }


def _normalized_query(value: str) -> str:
    return " ".join(value.split()).casefold()
