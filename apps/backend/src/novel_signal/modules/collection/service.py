from __future__ import annotations

import random
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from novel_signal.config import get_settings
from novel_signal.modules.collection.execution import CollectionWorkItem
from novel_signal.modules.collection.models import (
    CollectionAttempt,
    CollectionAttemptStatus,
    CollectionFailure,
    CollectionFailureType,
    CollectionJob,
    CollectionJobStatus,
    CollectionJobType,
    CollectionSourceTier,
    ParserVersion,
    QuarantineRecord,
    RawEvidence,
)
from novel_signal.modules.collection.repository import CollectionRepository

TERMINAL_JOB_STATUSES = {
    CollectionJobStatus.SUCCEEDED,
    CollectionJobStatus.FAILED,
    CollectionJobStatus.QUARANTINED,
    CollectionJobStatus.CANCELLED,
}


@dataclass(frozen=True)
class PlanningResult:
    jobs: tuple[CollectionJob, ...]
    created: int
    existing: int


@dataclass(frozen=True)
class AttemptClaim:
    job: CollectionJob
    attempt: CollectionAttempt
    item: CollectionWorkItem


@dataclass(frozen=True)
class FailureDecision:
    should_retry: bool
    retry_after_seconds: int | None


class CollectionJobNotFoundError(LookupError):
    pass


class CollectionJobStateError(RuntimeError):
    pass


def utc_now() -> datetime:
    return datetime.now(UTC)


def cadence_slot(at: datetime, cadence_minutes: int) -> datetime:
    if cadence_minutes <= 0:
        raise ValueError("cadence_minutes must be positive")
    current = at.astimezone(UTC)
    epoch_minutes = int(current.timestamp() // 60)
    slot_minutes = epoch_minutes - (epoch_minutes % cadence_minutes)
    return datetime.fromtimestamp(slot_minutes * 60, tz=UTC)


def idempotency_key(
    *,
    platform: str,
    job_type: CollectionJobType,
    subject_type: str,
    subject_id: uuid.UUID,
    scheduled_for: datetime,
) -> str:
    slot = scheduled_for.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{platform}:{job_type.value}:{subject_type}:{subject_id}:{slot}"


class CollectionPlanningService:
    """Turn S1/S2 tracking configuration into idempotent Week-1 collection jobs."""

    PRODUCT_DETAIL_CADENCE_MINUTES = 60

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = CollectionRepository(session)
        self.settings = get_settings()

    def plan_due(self, *, at: datetime | None = None) -> PlanningResult:
        now = (at or utc_now()).astimezone(UTC)
        jobs: list[CollectionJob] = []
        created = 0
        existing = 0

        # One SERP capture per keyword. If several targets share a keyword,
        # the shortest configured cadence wins so the capture is never duplicated.
        cadence_by_keyword: dict[uuid.UUID, int] = {}
        for target in self.repository.active_serp_targets():
            cadence_by_keyword[target.keyword_id] = min(
                target.cadence_minutes,
                cadence_by_keyword.get(target.keyword_id, target.cadence_minutes),
            )

        for keyword_id, cadence_minutes in cadence_by_keyword.items():
            scheduled_for = cadence_slot(now, cadence_minutes)
            key = idempotency_key(
                platform="amazon_in",
                job_type=CollectionJobType.SERP,
                subject_type="keyword",
                subject_id=keyword_id,
                scheduled_for=scheduled_for,
            )
            job = CollectionJob(
                idempotency_key=key,
                job_type=CollectionJobType.SERP,
                source_tier=CollectionSourceTier.PUBLIC_PAGE,
                platform="amazon_in",
                keyword_id=keyword_id,
                scheduled_for=scheduled_for,
                not_before=scheduled_for,
                max_attempts=self.settings.collector_max_attempts,
            )
            stored, was_created = self.repository.create_job_if_absent(job)
            jobs.append(stored)
            created += int(was_created)
            existing += int(not was_created)

        product_slot = cadence_slot(now, self.PRODUCT_DETAIL_CADENCE_MINUTES)
        for product in self.repository.active_products():
            key = idempotency_key(
                platform="amazon_in",
                job_type=CollectionJobType.PRODUCT_DETAIL,
                subject_type="product",
                subject_id=product.id,
                scheduled_for=product_slot,
            )
            job = CollectionJob(
                idempotency_key=key,
                job_type=CollectionJobType.PRODUCT_DETAIL,
                source_tier=CollectionSourceTier.PUBLIC_PAGE,
                platform="amazon_in",
                product_id=product.id,
                scheduled_for=product_slot,
                not_before=product_slot,
                max_attempts=self.settings.collector_max_attempts,
            )
            stored, was_created = self.repository.create_job_if_absent(job)
            jobs.append(stored)
            created += int(was_created)
            existing += int(not was_created)

        for competitor_product in self.repository.active_competitor_products():
            key = idempotency_key(
                platform="amazon_in",
                job_type=CollectionJobType.PRODUCT_DETAIL,
                subject_type="competitor_product",
                subject_id=competitor_product.id,
                scheduled_for=product_slot,
            )
            job = CollectionJob(
                idempotency_key=key,
                job_type=CollectionJobType.PRODUCT_DETAIL,
                source_tier=CollectionSourceTier.PUBLIC_PAGE,
                platform="amazon_in",
                competitor_product_id=competitor_product.id,
                scheduled_for=product_slot,
                not_before=product_slot,
                max_attempts=self.settings.collector_max_attempts,
            )
            stored, was_created = self.repository.create_job_if_absent(job)
            jobs.append(stored)
            created += int(was_created)
            existing += int(not was_created)

        return PlanningResult(jobs=tuple(jobs), created=created, existing=existing)


class CollectionLifecycleService:
    def __init__(
        self,
        session: Session,
        *,
        random_source: random.Random | None = None,
    ) -> None:
        self.session = session
        self.repository = CollectionRepository(session)
        self.random = random_source or random.SystemRandom()

    def get_job(self, job_id: uuid.UUID) -> CollectionJob:
        job = self.repository.get_job(job_id)
        if job is None:
            raise CollectionJobNotFoundError(str(job_id))
        return job

    def claim_attempt(
        self,
        job_id: uuid.UUID,
        *,
        worker_id: str | None = None,
        at: datetime | None = None,
    ) -> AttemptClaim | None:
        now = (at or utc_now()).astimezone(UTC)
        job = self.repository.get_job(job_id, for_update=True)
        if job is None:
            raise CollectionJobNotFoundError(str(job_id))
        if job.status in TERMINAL_JOB_STATUSES or job.status == CollectionJobStatus.RUNNING:
            return None
        if job.not_before is not None and job.not_before > now:
            return None
        if job.attempt_count >= job.max_attempts:
            job.status = CollectionJobStatus.FAILED
            job.completed_at = now
            job.last_error_code = job.last_error_code or "attempt_limit_reached"
            job.last_error_message = job.last_error_message or "Maximum collection attempts reached"
            self.session.flush()
            return None

        attempt_number = job.attempt_count + 1
        attempt = CollectionAttempt(
            job=job,
            attempt_number=attempt_number,
            status=CollectionAttemptStatus.RUNNING,
            worker_id=worker_id,
            started_at=now,
        )
        job.status = CollectionJobStatus.RUNNING
        job.attempt_count = attempt_number
        job.started_at = job.started_at or now
        job.completed_at = None
        job.not_before = None
        self.repository.add_attempt(attempt)

        item = CollectionWorkItem(
            job_id=job.id,
            attempt_id=attempt.id,
            job_type=job.job_type,
            platform=job.platform,
            keyword_id=job.keyword_id,
            product_id=job.product_id,
            competitor_product_id=job.competitor_product_id,
            tracking_target_id=job.tracking_target_id,
        )
        return AttemptClaim(job=job, attempt=attempt, item=item)

    def mark_succeeded(
        self,
        job_id: uuid.UUID,
        attempt_id: uuid.UUID,
        *,
        metadata: dict[str, Any] | None = None,
        at: datetime | None = None,
    ) -> CollectionJob:
        now = (at or utc_now()).astimezone(UTC)
        job = self.repository.get_job(job_id, for_update=True)
        if job is None:
            raise CollectionJobNotFoundError(str(job_id))
        attempt = next((item for item in job.attempts if item.id == attempt_id), None)
        if attempt is None:
            raise CollectionJobStateError("Collection attempt does not belong to the job")
        if attempt.status != CollectionAttemptStatus.RUNNING:
            raise CollectionJobStateError("Only a running collection attempt can succeed")

        attempt.status = CollectionAttemptStatus.SUCCEEDED
        attempt.finished_at = now
        attempt.retryable = False
        attempt.attempt_metadata = metadata
        job.status = CollectionJobStatus.SUCCEEDED
        job.completed_at = now
        job.last_error_code = None
        job.last_error_message = None
        self.session.flush()
        return job

    def mark_failed(
        self,
        job_id: uuid.UUID,
        attempt_id: uuid.UUID,
        *,
        failure_type: CollectionFailureType,
        code: str,
        message: str,
        retryable: bool,
        details: dict[str, Any] | None = None,
        at: datetime | None = None,
    ) -> FailureDecision:
        now = (at or utc_now()).astimezone(UTC)
        job = self.repository.get_job(job_id, for_update=True)
        if job is None:
            raise CollectionJobNotFoundError(str(job_id))
        attempt = next((item for item in job.attempts if item.id == attempt_id), None)
        if attempt is None:
            raise CollectionJobStateError("Collection attempt does not belong to the job")
        if attempt.status != CollectionAttemptStatus.RUNNING:
            raise CollectionJobStateError("Only a running collection attempt can fail")

        attempt.status = CollectionAttemptStatus.FAILED
        attempt.finished_at = now
        attempt.retryable = retryable
        attempt.error_code = code
        attempt.error_message = message
        self.repository.add_failure(
            CollectionFailure(
                job=job,
                attempt=attempt,
                failure_type=failure_type,
                failure_code=code,
                message=message,
                retryable=retryable,
                details=details,
                occurred_at=now,
            )
        )
        job.last_error_code = code
        job.last_error_message = message

        should_retry = retryable and job.attempt_count < job.max_attempts
        if should_retry:
            retry_after = self._retry_delay_seconds(job.attempt_count)
            job.status = CollectionJobStatus.PENDING
            job.not_before = now + timedelta(seconds=retry_after)
            job.completed_at = None
        else:
            retry_after = None
            job.status = CollectionJobStatus.FAILED
            job.completed_at = now
            job.not_before = None

        self.session.flush()
        return FailureDecision(
            should_retry=should_retry,
            retry_after_seconds=retry_after,
        )

    def mark_quarantined(
        self,
        job_id: uuid.UUID,
        attempt_id: uuid.UUID,
        *,
        raw_evidence: RawEvidence,
        parser_version: ParserVersion | None,
        failure_type: CollectionFailureType,
        reason_code: str,
        reason: str,
        schema_errors: list[dict[str, Any]] | None = None,
        parsed_payload: dict[str, Any] | list[Any] | None = None,
        at: datetime | None = None,
    ) -> CollectionJob:
        now = (at or utc_now()).astimezone(UTC)
        job = self.repository.get_job(job_id, for_update=True)
        if job is None:
            raise CollectionJobNotFoundError(str(job_id))
        attempt = next((item for item in job.attempts if item.id == attempt_id), None)
        if attempt is None:
            raise CollectionJobStateError("Collection attempt does not belong to the job")
        if attempt.status != CollectionAttemptStatus.RUNNING:
            raise CollectionJobStateError("Only a running collection attempt can be quarantined")

        attempt.status = CollectionAttemptStatus.QUARANTINED
        attempt.finished_at = now
        attempt.retryable = False
        attempt.error_code = reason_code
        attempt.error_message = reason
        self.repository.add_failure(
            CollectionFailure(
                job=job,
                attempt=attempt,
                failure_type=failure_type,
                failure_code=reason_code,
                message=reason,
                retryable=False,
                details={"raw_evidence_id": str(raw_evidence.id)},
                occurred_at=now,
            )
        )
        self.repository.add_quarantine(
            QuarantineRecord(
                job=job,
                attempt=attempt,
                raw_evidence=raw_evidence,
                parser_version=parser_version,
                reason_code=reason_code,
                reason=reason,
                schema_errors=schema_errors,
                parsed_payload=parsed_payload,
            )
        )
        job.status = CollectionJobStatus.QUARANTINED
        job.completed_at = now
        job.not_before = None
        job.last_error_code = reason_code
        job.last_error_message = reason
        self.session.flush()
        return job

    def _retry_delay_seconds(self, attempt_number: int) -> int:
        base_seconds = 30
        cap_seconds = 15 * 60
        exponential = min(base_seconds * (2 ** max(attempt_number - 1, 0)), cap_seconds)
        jitter = int(self.random.randint(0, max(1, exponential // 4)))
        return int(exponential + jitter)
