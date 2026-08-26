"""Publication of validated Amazon SERP parser records into S3 persistence."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from novel_signal.db import SessionLocal
from novel_signal.modules.collection.models import ParserVersion, RawEvidence
from novel_signal.modules.collection.pipeline import PublishContext
from novel_signal.modules.rank_visibility.errors import RankVisibilityConflictError
from novel_signal.modules.rank_visibility.models import DeviceProfile, SerpCapture, SerpResult
from novel_signal.modules.rank_visibility.schemas import CaptureIngest, SerpResultIn
from novel_signal.modules.rank_visibility.service import RankVisibilityService
from novel_signal.modules.universe.models import Marketplace


@dataclass(frozen=True)
class AmazonSerpPublicationConfig:
    """Explicit collection context that cannot be derived from parsed HTML."""

    keyword_id: UUID
    geo_code: str
    device_profile: DeviceProfile
    query: str
    page_number: int
    profile_id: str | None = None
    pincode: str | None = None
    location_label: str | None = None
    marketplace: Marketplace = Marketplace.AMAZON_IN

    def __post_init__(self) -> None:
        if not self.geo_code.strip() or not self.query.strip():
            raise ValueError("Amazon SERP publication requires geo code and query")
        if self.page_number < 1:
            raise ValueError("Amazon SERP publication page number must be positive")


class AmazonSerpPublisher:
    """Turn one validated Amazon SERP envelope into a RankVisibility capture."""

    def __init__(
        self,
        *,
        config: AmazonSerpPublicationConfig,
        session_factory: sessionmaker[Session] = SessionLocal,
    ) -> None:
        self.config = config
        self.session_factory = session_factory

    def publish(
        self,
        context: PublishContext,
        records: tuple[dict[str, Any], ...],
    ) -> dict[str, Any]:
        with self.session_factory() as session:
            raw_evidence = session.get(RawEvidence, context.raw_evidence_id)
            parser_version = session.get(ParserVersion, context.parser_version_id)
            if raw_evidence is None or parser_version is None:
                raise ValueError("Amazon SERP publication lineage is unavailable")

            metadata = _capture_metadata(
                context=context,
                config=self.config,
                raw_evidence=raw_evidence,
            )
            ingestion_key = _ingestion_key(context=context, config=self.config)
            payload = CaptureIngest(
                keyword_id=self.config.keyword_id,
                marketplace=self.config.marketplace,
                geo_code=self.config.geo_code,
                device_profile=self.config.device_profile,
                captured_at=context.captured_at,
                source_job_id=str(context.job_id),
                parser_version=parser_version.version,
                ingestion_key=ingestion_key,
                capture_metadata=metadata,
                results=list(records),
            )
            service = RankVisibilityService(session)
            try:
                capture = service.ingest(payload)
                return {
                    "capture_id": str(capture.id),
                    "ingestion_key": ingestion_key,
                    "published_records": capture.result_count,
                    "publication": "created",
                }
            except RankVisibilityConflictError:
                existing = service.repository.capture_by_ingestion_key(ingestion_key)
                if existing is None or not _is_same_publication(
                    capture=existing,
                    context=context,
                    config=self.config,
                ) or not _records_match(service.get_capture(existing.id), payload.results):
                    raise
                return {
                    "capture_id": str(existing.id),
                    "ingestion_key": ingestion_key,
                    "published_records": existing.result_count,
                    "publication": "existing",
                }


def _ingestion_key(*, context: PublishContext, config: AmazonSerpPublicationConfig) -> str:
    canonical = {
        "device_profile": config.device_profile.value,
        "keyword_id": str(config.keyword_id),
        "marketplace": config.marketplace.value,
        "page_number": config.page_number,
        "parser_version_id": str(context.parser_version_id),
        "raw_evidence_id": str(context.raw_evidence_id),
    }
    digest = hashlib.sha256(
        json.dumps(canonical, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()
    return f"amazon-serp:{digest}"


def _capture_metadata(
    *,
    context: PublishContext,
    config: AmazonSerpPublicationConfig,
    raw_evidence: RawEvidence,
) -> dict[str, object]:
    metadata: dict[str, object] = {
        "raw_evidence_id": str(context.raw_evidence_id),
        "parser_version_id": str(context.parser_version_id),
        "platform": context.platform,
        "page_type": context.page_type,
        "query": config.query,
        "page_number": config.page_number,
    }
    if raw_evidence.final_url:
        metadata["final_url"] = raw_evidence.final_url
    request_url = (raw_evidence.capture_metadata or {}).get("requested_url")
    if isinstance(request_url, str) and request_url:
        metadata["requested_url"] = request_url
    for field, value in (
        ("profile_id", config.profile_id),
        ("pincode", config.pincode),
        ("location_label", config.location_label),
    ):
        if value:
            metadata[field] = value
    return metadata


def _is_same_publication(
    *,
    capture: SerpCapture,
    context: PublishContext,
    config: AmazonSerpPublicationConfig,
) -> bool:
    metadata = capture.capture_metadata
    if not isinstance(metadata, dict):
        return False
    return (
        capture.keyword_id == config.keyword_id
        and capture.marketplace == config.marketplace
        and metadata.get("raw_evidence_id") == str(context.raw_evidence_id)
        and metadata.get("parser_version_id") == str(context.parser_version_id)
    )


def _records_match(existing: SerpCapture, incoming: list[SerpResultIn]) -> bool:
    if len(existing.results) != len(incoming):
        return False
    return all(
        _record_signature(persisted) == _incoming_signature(parsed)
        for persisted, parsed in zip(existing.results, incoming, strict=True)
    )


def _record_signature(record: SerpResult) -> tuple[object, ...]:
    return (
        record.absolute_position,
        record.page_number,
        record.marketplace_product_id,
        record.brand,
        record.placement_type.value,
        tuple(record.badges),
        record.amazons_choice_term,
        record.displayed_price,
        record.mrp,
        record.discount_percent,
        record.coupon,
        record.delivery_promise,
        record.rating,
        record.review_count,
        record.thumbnail_hash,
        record.result_metadata,
    )


def _incoming_signature(record: SerpResultIn) -> tuple[object, ...]:
    return (
        record.absolute_position,
        record.page_number,
        record.marketplace_product_id,
        record.brand,
        record.placement_type.value,
        tuple(badge.value for badge in record.badges),
        record.amazons_choice_term,
        record.displayed_price,
        record.mrp,
        record.discount_percent,
        record.coupon,
        record.delivery_promise,
        record.rating,
        record.review_count,
        record.thumbnail_hash,
        record.result_metadata,
    )
