from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from novel_signal.db import Base
from novel_signal.modules.universe.models import enum_column, utc_now


class CollectionJobType(StrEnum):
    SERP = "serp"
    PRODUCT_DETAIL = "product_detail"


class CollectionSourceTier(StrEnum):
    FIRST_PARTY_API = "first_party_api"
    LICENSED_DATA = "licensed_data"
    PUBLIC_PAGE = "public_page"


class CollectionJobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    QUARANTINED = "quarantined"
    CANCELLED = "cancelled"


class CollectionAttemptStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    QUARANTINED = "quarantined"


class CollectionFailureType(StrEnum):
    NETWORK = "network"
    TIMEOUT = "timeout"
    CHALLENGE = "challenge"
    HTTP_ERROR = "http_error"
    STORAGE_ERROR = "storage_error"
    PARSE_ERROR = "parse_error"
    VALIDATION_ERROR = "validation_error"
    UNKNOWN = "unknown"


class RawEvidenceType(StrEnum):
    RESPONSE_BODY = "response_body"
    SCREENSHOT = "screenshot"


class QuarantineStatus(StrEnum):
    QUARANTINED = "quarantined"
    RELEASED = "released"
    DISCARDED = "discarded"


class DataQualityCheckType(StrEnum):
    FRESHNESS = "freshness"
    COMPLETENESS = "completeness"
    CONSISTENCY = "consistency"
    FIELD_FILL_RATE = "field_fill_rate"
    ROW_COUNT = "row_count"
    VALUE_DISTRIBUTION = "value_distribution"


class DataQualityStatus(StrEnum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


class CollectionJob(Base):
    __tablename__ = "collection_jobs"
    __table_args__ = (
        CheckConstraint("length(trim(idempotency_key)) > 0", name="idempotency_key_not_blank"),
        CheckConstraint("length(trim(platform)) > 0", name="platform_not_blank"),
        CheckConstraint("attempt_count >= 0", name="attempt_count_nonnegative"),
        CheckConstraint("max_attempts > 0", name="max_attempts_positive"),
        CheckConstraint(
            "keyword_id IS NOT NULL OR product_id IS NOT NULL OR "
            "competitor_product_id IS NOT NULL OR tracking_target_id IS NOT NULL",
            name="subject_required",
        ),
        CheckConstraint(
            "NOT (product_id IS NOT NULL AND competitor_product_id IS NOT NULL)",
            name="single_product_subject",
        ),
        UniqueConstraint("idempotency_key", name="uq_collection_jobs_idempotency_key"),
        Index("ix_collection_jobs_status_scheduled_for", "status", "scheduled_for"),
        Index("ix_collection_jobs_platform_job_type", "platform", "job_type"),
        Index("ix_collection_jobs_keyword_id", "keyword_id"),
        Index("ix_collection_jobs_product_id", "product_id"),
        Index("ix_collection_jobs_competitor_product_id", "competitor_product_id"),
        Index("ix_collection_jobs_tracking_target_id", "tracking_target_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    job_type: Mapped[CollectionJobType] = mapped_column(
        enum_column(CollectionJobType, "collection_job_type"), nullable=False
    )
    source_tier: Mapped[CollectionSourceTier] = mapped_column(
        enum_column(CollectionSourceTier, "collection_source_tier"), nullable=False
    )
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    keyword_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("keywords.id", ondelete="RESTRICT")
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT")
    )
    competitor_product_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("competitor_products.id", ondelete="RESTRICT")
    )
    tracking_target_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tracking_targets.id", ondelete="RESTRICT")
    )
    status: Mapped[CollectionJobStatus] = mapped_column(
        enum_column(CollectionJobStatus, "collection_job_status"),
        default=CollectionJobStatus.PENDING,
        server_default=CollectionJobStatus.PENDING.value,
        nullable=False,
    )
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    not_before: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    max_attempts: Mapped[int] = mapped_column(
        Integer, default=3, server_default="3", nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(100))
    last_error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        server_default=func.now(),
        nullable=False,
    )

    attempts: Mapped[list[CollectionAttempt]] = relationship(
        back_populates="job", order_by="CollectionAttempt.attempt_number"
    )
    failures: Mapped[list[CollectionFailure]] = relationship(
        back_populates="job", order_by="CollectionFailure.occurred_at"
    )
    raw_evidence: Mapped[list[RawEvidence]] = relationship(
        back_populates="job", order_by="RawEvidence.captured_at"
    )
    quarantine_records: Mapped[list[QuarantineRecord]] = relationship(
        back_populates="job", order_by="QuarantineRecord.created_at"
    )


class CollectionAttempt(Base):
    __tablename__ = "collection_attempts"
    __table_args__ = (
        CheckConstraint("attempt_number > 0", name="attempt_number_positive"),
        UniqueConstraint("job_id", "attempt_number", name="uq_collection_attempts_job_number"),
        Index("ix_collection_attempts_job_id", "job_id"),
        Index("ix_collection_attempts_status_started_at", "status", "started_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("collection_jobs.id", ondelete="RESTRICT"), nullable=False
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[CollectionAttemptStatus] = mapped_column(
        enum_column(CollectionAttemptStatus, "collection_attempt_status"), nullable=False
    )
    worker_id: Mapped[str | None] = mapped_column(String(255))
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retryable: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)
    attempt_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    job: Mapped[CollectionJob] = relationship(back_populates="attempts")
    failures: Mapped[list[CollectionFailure]] = relationship(back_populates="attempt")
    raw_evidence: Mapped[list[RawEvidence]] = relationship(back_populates="attempt")
    quarantine_records: Mapped[list[QuarantineRecord]] = relationship(back_populates="attempt")


class CollectionFailure(Base):
    __tablename__ = "collection_failures"
    __table_args__ = (
        CheckConstraint("length(trim(message)) > 0", name="message_not_blank"),
        Index("ix_collection_failures_job_occurred_at", "job_id", "occurred_at"),
        Index("ix_collection_failures_failure_type", "failure_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("collection_jobs.id", ondelete="RESTRICT"), nullable=False
    )
    attempt_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("collection_attempts.id", ondelete="SET NULL")
    )
    failure_type: Mapped[CollectionFailureType] = mapped_column(
        enum_column(CollectionFailureType, "collection_failure_type"), nullable=False
    )
    failure_code: Mapped[str | None] = mapped_column(String(100))
    message: Mapped[str] = mapped_column(Text, nullable=False)
    retryable: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )

    job: Mapped[CollectionJob] = relationship(back_populates="failures")
    attempt: Mapped[CollectionAttempt | None] = relationship(back_populates="failures")


class RawEvidence(Base):
    __tablename__ = "raw_evidence"
    __table_args__ = (
        CheckConstraint("length(sha256) = 64", name="sha256_length"),
        CheckConstraint("byte_length >= 0", name="byte_length_nonnegative"),
        CheckConstraint("length(trim(storage_bucket)) > 0", name="storage_bucket_not_blank"),
        CheckConstraint("length(trim(object_key)) > 0", name="object_key_not_blank"),
        Index("ix_raw_evidence_job_captured_at", "job_id", "captured_at"),
        Index("ix_raw_evidence_sha256", "sha256"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("collection_jobs.id", ondelete="RESTRICT"), nullable=False
    )
    attempt_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("collection_attempts.id", ondelete="SET NULL")
    )
    evidence_type: Mapped[RawEvidenceType] = mapped_column(
        enum_column(RawEvidenceType, "raw_evidence_type"),
        default=RawEvidenceType.RESPONSE_BODY,
        server_default=RawEvidenceType.RESPONSE_BODY.value,
        nullable=False,
    )
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_bucket: Mapped[str] = mapped_column(String(255), nullable=False)
    object_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    content_type: Mapped[str] = mapped_column(String(255), nullable=False)
    byte_length: Mapped[int] = mapped_column(Integer, nullable=False)
    compressed: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    final_url: Mapped[str | None] = mapped_column(String(2048))
    challenge_detected: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    capture_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )

    job: Mapped[CollectionJob] = relationship(back_populates="raw_evidence")
    attempt: Mapped[CollectionAttempt | None] = relationship(back_populates="raw_evidence")
    quarantine_records: Mapped[list[QuarantineRecord]] = relationship(back_populates="raw_evidence")


class ParserVersion(Base):
    __tablename__ = "parser_versions"
    __table_args__ = (
        CheckConstraint("length(trim(platform)) > 0", name="platform_not_blank"),
        CheckConstraint("length(trim(page_type)) > 0", name="page_type_not_blank"),
        CheckConstraint("length(trim(version)) > 0", name="version_not_blank"),
        UniqueConstraint(
            "platform", "page_type", "version", name="uq_parser_versions_platform_page_version"
        ),
        Index("ix_parser_versions_platform_page_active", "platform", "page_type", "active"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    page_type: Mapped[str] = mapped_column(String(80), nullable=False)
    version: Mapped[str] = mapped_column(String(100), nullable=False)
    code_checksum: Mapped[str | None] = mapped_column(String(64))
    active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )
    deployed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )

    quarantine_records: Mapped[list[QuarantineRecord]] = relationship(
        back_populates="parser_version"
    )


class QuarantineRecord(Base):
    __tablename__ = "quarantine_records"
    __table_args__ = (
        CheckConstraint("length(trim(reason_code)) > 0", name="reason_code_not_blank"),
        CheckConstraint("length(trim(reason)) > 0", name="reason_not_blank"),
        Index("ix_quarantine_records_status_created_at", "status", "created_at"),
        Index("ix_quarantine_records_job_id", "job_id"),
        Index("ix_quarantine_records_raw_evidence_id", "raw_evidence_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("collection_jobs.id", ondelete="RESTRICT"), nullable=False
    )
    attempt_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("collection_attempts.id", ondelete="SET NULL")
    )
    raw_evidence_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("raw_evidence.id", ondelete="RESTRICT"), nullable=False
    )
    parser_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("parser_versions.id", ondelete="RESTRICT")
    )
    status: Mapped[QuarantineStatus] = mapped_column(
        enum_column(QuarantineStatus, "quarantine_status"),
        default=QuarantineStatus.QUARANTINED,
        server_default=QuarantineStatus.QUARANTINED.value,
        nullable=False,
    )
    reason_code: Mapped[str] = mapped_column(String(100), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    schema_errors: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    parsed_payload: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_note: Mapped[str | None] = mapped_column(Text)

    job: Mapped[CollectionJob] = relationship(back_populates="quarantine_records")
    attempt: Mapped[CollectionAttempt | None] = relationship(back_populates="quarantine_records")
    raw_evidence: Mapped[RawEvidence] = relationship(back_populates="quarantine_records")
    parser_version: Mapped[ParserVersion | None] = relationship(
        back_populates="quarantine_records"
    )


class DataQualityCheck(Base):
    __tablename__ = "data_quality_checks"
    __table_args__ = (
        CheckConstraint("length(trim(scope_type)) > 0", name="scope_type_not_blank"),
        CheckConstraint("length(trim(scope_key)) > 0", name="scope_key_not_blank"),
        CheckConstraint(
            "window_end IS NULL OR window_start IS NULL OR window_end >= window_start",
            name="window_order",
        ),
        CheckConstraint("sample_size IS NULL OR sample_size >= 0", name="sample_size_nonnegative"),
        Index("ix_data_quality_checks_scope_created_at", "scope_type", "scope_key", "created_at"),
        Index("ix_data_quality_checks_type_status", "check_type", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    check_type: Mapped[DataQualityCheckType] = mapped_column(
        enum_column(DataQualityCheckType, "data_quality_check_type"), nullable=False
    )
    status: Mapped[DataQualityStatus] = mapped_column(
        enum_column(DataQualityStatus, "data_quality_status"), nullable=False
    )
    scope_type: Mapped[str] = mapped_column(String(80), nullable=False)
    scope_key: Mapped[str] = mapped_column(String(255), nullable=False)
    window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    observed_value: Mapped[dict[str, Any] | list[Any] | float | int | str | None] = mapped_column(
        JSON
    )
    expected_value: Mapped[dict[str, Any] | list[Any] | float | int | str | None] = mapped_column(
        JSON
    )
    sample_size: Mapped[int | None] = mapped_column(Integer)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
