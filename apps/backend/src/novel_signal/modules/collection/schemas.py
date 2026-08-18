from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from novel_signal.modules.collection.models import CollectionJobStatus, CollectionJobType


class CollectionJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    idempotency_key: str
    job_type: CollectionJobType
    platform: str
    keyword_id: uuid.UUID | None
    product_id: uuid.UUID | None
    competitor_product_id: uuid.UUID | None
    tracking_target_id: uuid.UUID | None
    status: CollectionJobStatus
    scheduled_for: datetime
    not_before: datetime | None
    attempt_count: int
    max_attempts: int
    started_at: datetime | None
    completed_at: datetime | None
    last_error_code: str | None
    last_error_message: str | None
    created_at: datetime
    updated_at: datetime


class CollectionJobList(BaseModel):
    items: list[CollectionJobRead]
    total: int
    limit: int
    offset: int


class CollectionPlanResult(BaseModel):
    created: int
    existing: int
    job_ids: list[uuid.UUID]


class CollectionDispatchResult(BaseModel):
    dispatched: int
    job_ids: list[uuid.UUID]


class RawEvidenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_id: uuid.UUID
    attempt_id: uuid.UUID | None
    evidence_type: str
    sha256: str
    storage_bucket: str
    object_key: str
    content_type: str
    byte_length: int
    compressed: bool
    final_url: str | None
    challenge_detected: bool
    capture_metadata: dict[str, object] | None
    captured_at: datetime


class RawEvidenceList(BaseModel):
    items: list[RawEvidenceRead]
    total: int
    limit: int
    offset: int


class QuarantineRecordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_id: uuid.UUID
    attempt_id: uuid.UUID | None
    raw_evidence_id: uuid.UUID
    parser_version_id: uuid.UUID | None
    status: str
    reason_code: str
    reason: str
    schema_errors: list[dict[str, object]] | None
    parsed_payload: dict[str, object] | list[object] | None
    created_at: datetime
    resolved_at: datetime | None
    resolution_note: str | None


class QuarantineRecordList(BaseModel):
    items: list[QuarantineRecordRead]
    total: int
    limit: int
    offset: int


class DataQualityCheckRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    check_type: str
    status: str
    scope_type: str
    scope_key: str
    observed_value: object | None
    expected_value: object | None
    sample_size: int | None
    details: dict[str, object] | None
    created_at: datetime


class DataQualityCheckList(BaseModel):
    items: list[DataQualityCheckRead]
    total: int
    limit: int
    offset: int


class CollectionHealthRead(BaseModel):
    window_hours: int
    scheduled: int
    succeeded: int
    failed: int
    quarantined: int
    running: int
    pending: int
    terminal: int
    success_ratio: float | None
    challenge_count: int
    challenge_ratio: float | None
    parser_canary_failures: int
    latest_success_at: datetime | None
    freshness_minutes: float | None
    freshness_status: str
    completeness_status: str
    overall_status: str


class DependencyReadiness(BaseModel):
    status: str
    detail: str | None = None


class CollectionReadinessRead(BaseModel):
    status: str
    postgres: DependencyReadiness
    redis: DependencyReadiness
    object_store: DependencyReadiness
    celery: DependencyReadiness


class CollectionFailureList(BaseModel):
    items: list[CollectionJobRead]
    total: int
    limit: int
    offset: int


class RawRetentionCandidateRead(BaseModel):
    id: uuid.UUID
    job_id: uuid.UUID
    captured_at: datetime
    storage_bucket: str
    object_key: str
    byte_length: int


class RawRetentionRead(BaseModel):
    retention_days: int
    cutoff: datetime
    candidates: list[RawRetentionCandidateRead]
    candidate_count: int
