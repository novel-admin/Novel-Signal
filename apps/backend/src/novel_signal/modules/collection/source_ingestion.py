from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from novel_signal.modules.collection.models import ParserVersion, RawEvidence, RawEvidenceType
from novel_signal.modules.collection.repository import CollectionRepository
from novel_signal.modules.collection.storage import RawObjectStore
from novel_signal.sources.base import RawSourcePage


def persist_raw_source_page(
    session: Session,
    *,
    object_store: RawObjectStore,
    job_id: uuid.UUID,
    attempt_id: uuid.UUID,
    platform: str,
    page: RawSourcePage,
    captured_at: datetime | None = None,
) -> RawEvidence:
    stored = object_store.put_raw(
        platform=platform,
        page_type=page.resource_type,
        body=page.body,
    )
    evidence = RawEvidence(
        job_id=job_id,
        attempt_id=attempt_id,
        evidence_type=RawEvidenceType.RESPONSE_BODY,
        sha256=stored.sha256,
        storage_bucket=stored.bucket,
        object_key=stored.object_key,
        content_type=page.content_type,
        byte_length=stored.byte_length,
        compressed=True,
        capture_metadata={
            "resource_type": page.resource_type,
            "request_fingerprint": page.request_fingerprint,
            "compressed_byte_length": stored.compressed_byte_length,
        },
        captured_at=captured_at or datetime.now(UTC),
    )
    session.add(evidence)
    session.commit()  # required durability boundary before parsing or normalization
    session.refresh(evidence)
    return evidence


def ensure_parser_version(
    session: Session, *, platform: str, page_type: str, version: str
) -> ParserVersion:
    repository = CollectionRepository(session)
    existing = repository.get_parser_version(platform, page_type, version)
    if existing:
        return existing
    parser = ParserVersion(
        platform=platform,
        page_type=page_type,
        version=version,
        active=True,
        deployed_at=datetime.now(UTC),
    )
    session.add(parser)
    session.commit()
    session.refresh(parser)
    return parser
