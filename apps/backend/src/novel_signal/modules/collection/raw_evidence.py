from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from novel_signal.db import SessionLocal
from novel_signal.modules.collection.execution import CollectionExecutionError
from novel_signal.modules.collection.models import (
    CollectionFailureType,
    RawEvidence,
    RawEvidenceType,
)
from novel_signal.modules.collection.storage import RawObjectStore, S3RawObjectStore


class RawEvidenceWriter:
    """Persist one immutable response body through the shared S12 durability boundary."""

    def __init__(
        self,
        *,
        object_store: RawObjectStore | None = None,
        session_factory: sessionmaker[Session] = SessionLocal,
    ) -> None:
        self.object_store = object_store or S3RawObjectStore()
        self.session_factory = session_factory

    def persist(
        self,
        *,
        job_id: uuid.UUID,
        attempt_id: uuid.UUID,
        platform: str,
        page_type: str,
        body: bytes,
        content_type: str,
        final_url: str | None,
        challenge_detected: bool,
        capture_metadata: dict[str, Any],
        captured_at: datetime | None = None,
    ) -> RawEvidence:
        captured = (captured_at or datetime.now(UTC)).astimezone(UTC)
        try:
            stored = self.object_store.put_raw(
                platform=platform,
                page_type=page_type,
                body=body,
            )
        except Exception as error:
            raise CollectionExecutionError(
                "Raw evidence storage failed before persistence",
                failure_type=CollectionFailureType.STORAGE_ERROR,
                code="raw_storage_failed",
                retryable=True,
                details={"exception_type": type(error).__name__},
            ) from error

        evidence = RawEvidence(
            job_id=job_id,
            attempt_id=attempt_id,
            evidence_type=RawEvidenceType.RESPONSE_BODY,
            sha256=stored.sha256,
            storage_bucket=stored.bucket,
            object_key=stored.object_key,
            content_type=content_type,
            byte_length=stored.byte_length,
            compressed=True,
            final_url=final_url,
            challenge_detected=challenge_detected,
            capture_metadata={
                **capture_metadata,
                "compressed_byte_length": stored.compressed_byte_length,
            },
            captured_at=captured,
        )
        try:
            with self.session_factory() as session:
                session.add(evidence)
                session.commit()  # intentional raw-evidence durability boundary
                session.refresh(evidence)
        except Exception as error:
            raise CollectionExecutionError(
                "Raw evidence database persistence failed",
                failure_type=CollectionFailureType.STORAGE_ERROR,
                code="raw_evidence_persistence_failed",
                retryable=True,
                details={"exception_type": type(error).__name__},
            ) from error
        return evidence
