from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy.orm import Session, sessionmaker

from novel_signal.collectors.base import CaptureRequest, CaptureResult
from novel_signal.db import SessionLocal
from novel_signal.modules.collection.execution import (
    CollectionExecutionError,
    CollectionExecutionResult,
    QuarantineDecision,
)
from novel_signal.modules.collection.models import (
    CollectionFailureType,
    DataQualityCheck,
    DataQualityCheckType,
    DataQualityStatus,
    ParserVersion,
    RawEvidence,
)
from novel_signal.modules.collection.parsing import (
    EnvelopeValidator,
    ParserNotRegisteredError,
    ParserRegistry,
    ValidationResult,
)
from novel_signal.modules.collection.raw_evidence import RawEvidenceWriter
from novel_signal.modules.collection.repository import CollectionRepository
from novel_signal.modules.collection.storage import RawObjectStore, S3RawObjectStore


@dataclass(frozen=True)
class PublishContext:
    job_id: uuid.UUID
    attempt_id: uuid.UUID
    raw_evidence_id: uuid.UUID
    parser_version_id: uuid.UUID
    platform: str
    page_type: str
    captured_at: datetime


class NormalizedPublisher(Protocol):
    def publish(
        self,
        context: PublishContext,
        records: tuple[dict[str, Any], ...],
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class NoopPublisher:
    metadata: dict[str, Any] = field(default_factory=dict)

    def publish(
        self,
        context: PublishContext,
        records: tuple[dict[str, Any], ...],
    ) -> dict[str, Any]:
        return {**self.metadata, "published_records": len(records)}


class EvidencePipeline:
    """Raw-first capture gate: durable evidence -> parse -> validate -> publish/quarantine."""

    def __init__(
        self,
        *,
        parser_registry: ParserRegistry,
        object_store: RawObjectStore | None = None,
        session_factory: sessionmaker[Session] = SessionLocal,
    ) -> None:
        self.parser_registry = parser_registry
        self.object_store = object_store or S3RawObjectStore()
        self.session_factory = session_factory
        self.raw_evidence_writer = RawEvidenceWriter(
            object_store=self.object_store,
            session_factory=self.session_factory,
        )

    def process(
        self,
        *,
        job_id: uuid.UUID,
        attempt_id: uuid.UUID,
        platform: str,
        request: CaptureRequest,
        capture: CaptureResult,
        validator: EnvelopeValidator,
        publisher: NormalizedPublisher,
        captured_at: datetime | None = None,
    ) -> CollectionExecutionResult:
        captured = (captured_at or datetime.now(UTC)).astimezone(UTC)
        raw = self._persist_raw_first(
            job_id=job_id,
            attempt_id=attempt_id,
            platform=platform,
            request=request,
            capture=capture,
            captured_at=captured,
        )

        if capture.challenge_detected:
            raise CollectionExecutionError(
                "Marketplace challenge detected; raw evidence retained and collection stopped",
                failure_type=CollectionFailureType.CHALLENGE,
                code="challenge_detected",
                retryable=False,
                details={"raw_evidence_id": str(raw.id)},
            )

        try:
            parser = self.parser_registry.get(platform, request.page_type)
        except ParserNotRegisteredError as error:
            return CollectionExecutionResult(
                metadata={"raw_evidence_id": str(raw.id)},
                quarantine=QuarantineDecision(
                    raw_evidence_id=raw.id,
                    parser_version_id=None,
                    failure_type=CollectionFailureType.PARSE_ERROR,
                    reason_code="parser_not_registered",
                    reason=str(error),
                    schema_errors=({"code": "parser_not_registered"},),
                    parsed_payload=None,
                ),
            )

        parser_version = self._ensure_parser_version(
            platform=platform,
            page_type=request.page_type,
            version=parser.version,
        )

        try:
            envelope = parser.parse(capture.body)
        except Exception as error:
            self._record_quality(
                platform=platform,
                page_type=request.page_type,
                check_type=DataQualityCheckType.CONSISTENCY,
                status=DataQualityStatus.FAIL,
                observed={"exception_type": type(error).__name__},
                expected={"parse_success": True},
                sample_size=0,
                details={"message": str(error)},
            )
            return CollectionExecutionResult(
                metadata={"raw_evidence_id": str(raw.id)},
                quarantine=QuarantineDecision(
                    raw_evidence_id=raw.id,
                    parser_version_id=parser_version.id,
                    failure_type=CollectionFailureType.PARSE_ERROR,
                    reason_code="parser_exception",
                    reason=str(error) or type(error).__name__,
                    schema_errors=(
                        {"code": "parser_exception", "exception_type": type(error).__name__},
                    ),
                    parsed_payload=None,
                ),
            )

        validation = validator.validate(
            envelope,
            expected_page_type=request.page_type,
            expected_parser_version=parser.version,
        )
        self._record_validation_quality(
            platform=platform,
            page_type=request.page_type,
            validation=validation,
        )
        if not validation.valid:
            return CollectionExecutionResult(
                metadata={"raw_evidence_id": str(raw.id)},
                quarantine=QuarantineDecision(
                    raw_evidence_id=raw.id,
                    parser_version_id=parser_version.id,
                    failure_type=CollectionFailureType.VALIDATION_ERROR,
                    reason_code="schema_validation_failed",
                    reason="Parsed output failed schema/completeness validation",
                    schema_errors=tuple(issue.as_dict() for issue in validation.issues),
                    parsed_payload=list(envelope.records),
                ),
            )

        published = publisher.publish(
            PublishContext(
                job_id=job_id,
                attempt_id=attempt_id,
                raw_evidence_id=raw.id,
                parser_version_id=parser_version.id,
                platform=platform,
                page_type=request.page_type,
                captured_at=captured,
            ),
            envelope.records,
        )
        return CollectionExecutionResult(
            metadata={
                "raw_evidence_id": str(raw.id),
                "parser_version_id": str(parser_version.id),
                "parser_version": parser.version,
                "row_count": len(envelope.records),
                **published,
            }
        )

    def _persist_raw_first(
        self,
        *,
        job_id: uuid.UUID,
        attempt_id: uuid.UUID,
        platform: str,
        request: CaptureRequest,
        capture: CaptureResult,
        captured_at: datetime,
    ) -> RawEvidence:
        return self.raw_evidence_writer.persist(
            job_id=job_id,
            attempt_id=attempt_id,
            platform=platform,
            page_type=request.page_type,
            body=capture.body,
            content_type=capture.content_type,
            final_url=capture.final_url,
            challenge_detected=capture.challenge_detected,
            capture_metadata={
                "target_id": request.target_id,
                "page_type": request.page_type,
                "requested_url": request.url,
            },
            captured_at=captured_at,
        )

    def _ensure_parser_version(
        self, *, platform: str, page_type: str, version: str
    ) -> ParserVersion:
        with self.session_factory() as session:
            repository = CollectionRepository(session)
            existing = repository.get_parser_version(platform, page_type, version)
            if existing is not None:
                return existing
            parser_version = ParserVersion(
                platform=platform,
                page_type=page_type,
                version=version,
                code_checksum=None,
                active=True,
                deployed_at=datetime.now(UTC),
            )
            session.add(parser_version)
            session.commit()
            session.refresh(parser_version)
            return parser_version

    def _record_validation_quality(
        self, *, platform: str, page_type: str, validation: ValidationResult
    ) -> None:
        self._record_quality(
            platform=platform,
            page_type=page_type,
            check_type=DataQualityCheckType.FIELD_FILL_RATE,
            status=DataQualityStatus.PASS if validation.valid else DataQualityStatus.FAIL,
            observed={"field_fill_rate": validation.field_fill_rate},
            expected={"field_fill_rate": 1.0},
            sample_size=validation.row_count,
            details={"issues": [issue.as_dict() for issue in validation.issues]},
        )
        self._record_quality(
            platform=platform,
            page_type=page_type,
            check_type=DataQualityCheckType.ROW_COUNT,
            status=DataQualityStatus.PASS if validation.row_count > 0 else DataQualityStatus.FAIL,
            observed={"row_count": validation.row_count},
            expected={"minimum_rows": 1},
            sample_size=validation.row_count,
            details=None,
        )

    def _record_quality(
        self,
        *,
        platform: str,
        page_type: str,
        check_type: DataQualityCheckType,
        status: DataQualityStatus,
        observed: dict[str, Any],
        expected: dict[str, Any],
        sample_size: int,
        details: dict[str, Any] | None,
    ) -> None:
        with self.session_factory() as session:
            session.add(
                DataQualityCheck(
                    check_type=check_type,
                    status=status,
                    scope_type="parser",
                    scope_key=f"{platform}:{page_type}",
                    observed_value=observed,
                    expected_value=expected,
                    sample_size=sample_size,
                    details=details,
                )
            )
            session.commit()
