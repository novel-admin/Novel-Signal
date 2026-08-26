from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from novel_signal.db import SessionLocal
from novel_signal.modules.collection.models import RawEvidence
from novel_signal.modules.collection.pipeline import PublishContext
from novel_signal.modules.keywords.models import (
    IntentCluster,
    Keyword,
    KeywordSource,
    KeywordSourceType,
    KeywordTrackingStatus,
)
from novel_signal.modules.keywords.repository import KeywordRepository
from novel_signal.modules.keywords.schemas import normalize_keyword
from novel_signal.modules.universe.models import Marketplace, TrackingTier


class KeywordPublicationError(ValueError):
    """Raised when a parsed record cannot be safely published into S2."""


@dataclass(frozen=True)
class KeywordPublicationConfig:
    marketplace: Marketplace
    source_type: KeywordSourceType
    default_tier: TrackingTier
    default_tracking_status: KeywordTrackingStatus
    default_intent_cluster: IntentCluster


@dataclass(frozen=True)
class _KeywordObservation:
    keyword_text: str
    normalized_text: str
    metadata: dict[str, object]


class KeywordEvidencePublisher:
    """Publish validated parser output while retaining S12 raw-evidence lineage."""

    def __init__(
        self,
        *,
        config: KeywordPublicationConfig,
        session_factory: sessionmaker[Session] = SessionLocal,
    ) -> None:
        self.config = config
        self.session_factory = session_factory

    def publish(
        self,
        context: PublishContext,
        records: tuple[dict[str, Any], ...],
    ) -> dict[str, Any]:
        observations = tuple(_observation_from_record(record) for record in records)
        with self.session_factory.begin() as session:
            raw_evidence = session.get(RawEvidence, context.raw_evidence_id)
            if raw_evidence is None:
                raise KeywordPublicationError("Referenced raw evidence does not exist")
            if (
                raw_evidence.job_id != context.job_id
                or raw_evidence.attempt_id != context.attempt_id
            ):
                raise KeywordPublicationError("Raw evidence does not match the publication context")

            repository = KeywordRepository(session)
            created_keywords = 0
            added_sources = 0
            for observation in observations:
                keyword = repository.get_keyword_by_identity(
                    self.config.marketplace,
                    observation.normalized_text,
                )
                if keyword is None:
                    keyword = Keyword(
                        keyword_text=observation.keyword_text,
                        normalized_text=observation.normalized_text,
                        marketplace=self.config.marketplace,
                        tier=self.config.default_tier,
                        tracking_status=self.config.default_tracking_status,
                        intent_cluster=self.config.default_intent_cluster,
                    )
                    session.add(keyword)
                    session.flush()
                    created_keywords += 1

                source_reference = _source_reference(
                    source_type=self.config.source_type,
                    raw_evidence_id=context.raw_evidence_id,
                    parser_version_id=context.parser_version_id,
                    normalized_text=observation.normalized_text,
                    observation_metadata=observation.metadata,
                )
                if any(
                    source.source_type == self.config.source_type
                    and source.source_reference == source_reference
                    for source in keyword.sources
                ):
                    continue
                keyword.sources.append(
                    KeywordSource(
                        source_type=self.config.source_type,
                        source_reference=source_reference,
                        source_metadata=_source_metadata(
                            raw_evidence=raw_evidence,
                            context=context,
                            source_type=self.config.source_type,
                            observation_metadata=observation.metadata,
                        ),
                    )
                )
                added_sources += 1

        return {
            "created_keywords": created_keywords,
            "published_keyword_sources": added_sources,
        }


def _observation_from_record(record: dict[str, Any]) -> _KeywordObservation:
    keyword_text = record.get("keyword_text")
    if not isinstance(keyword_text, str) or not keyword_text.strip():
        raise KeywordPublicationError("Parsed keyword record is missing keyword_text")
    metadata = record.get("observation_metadata", {})
    if not isinstance(metadata, dict):
        raise KeywordPublicationError("Parsed keyword observation metadata must be an object")
    normalized_metadata = _json_object(metadata, "Parsed keyword observation metadata")
    clean_text = " ".join(keyword_text.split())
    return _KeywordObservation(
        keyword_text=clean_text,
        normalized_text=normalize_keyword(clean_text),
        metadata=normalized_metadata,
    )


def _source_reference(
    *,
    source_type: KeywordSourceType,
    raw_evidence_id: uuid.UUID,
    parser_version_id: uuid.UUID,
    normalized_text: str,
    observation_metadata: dict[str, object],
) -> str:
    """Return ``{source}:raw:{id}:parser:{id}:obs:{sha256}`` for replay-safe provenance."""
    observation_digest = hashlib.sha256(
        json.dumps(
            {
                "keyword": normalized_text,
                "observation": observation_metadata,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    return (
        f"{source_type.value}:raw:{raw_evidence_id}:parser:{parser_version_id}:"
        f"obs:{observation_digest}"
    )


def _source_metadata(
    *,
    raw_evidence: RawEvidence,
    context: PublishContext,
    source_type: KeywordSourceType,
    observation_metadata: dict[str, object],
) -> dict[str, object]:
    metadata: dict[str, object] = {
        "raw_evidence_id": str(context.raw_evidence_id),
        "parser_version_id": str(context.parser_version_id),
        "source_type": source_type.value,
        "resource_type": context.page_type,
        "captured_at": context.captured_at.astimezone(UTC).isoformat(),
        "observation": observation_metadata,
    }
    capture_metadata = raw_evidence.capture_metadata
    if isinstance(capture_metadata, dict):
        raw_source_type = capture_metadata.get("source_type")
        if isinstance(raw_source_type, str):
            metadata["raw_source_type"] = raw_source_type
        resource_type = capture_metadata.get("resource_type")
        if isinstance(resource_type, str):
            metadata["resource_type"] = resource_type
        request_fingerprint = capture_metadata.get("request_fingerprint")
        if isinstance(request_fingerprint, str):
            metadata["request_fingerprint"] = request_fingerprint
    return metadata


def _json_object(value: dict[str, Any], context: str) -> dict[str, object]:
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"))
        decoded = json.loads(encoded)
    except (TypeError, ValueError) as error:
        raise KeywordPublicationError(f"{context} must be JSON serializable") from error
    if not isinstance(decoded, dict):
        raise KeywordPublicationError(f"{context} must be an object")
    return decoded
