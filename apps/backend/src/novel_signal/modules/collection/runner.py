"""Database-backed collection runner for scheduled hosts such as Render Cron.

This module deliberately has no broker dependency.  The scheduler plans work in
PostgreSQL, claims each job through the existing lifecycle service, and records
every terminal result before moving to the next job.
"""

from __future__ import annotations

import socket
import uuid
from dataclasses import dataclass
from typing import Any

from novel_signal.db import SessionLocal
from novel_signal.modules.collection.amazon_product_executor import AmazonProductExecutor
from novel_signal.modules.collection.amazon_serp_executor import AmazonSerpExecutor
from novel_signal.modules.collection.execution import (
    CollectionExecutionError,
    execute_async,
    get_executor,
    register_executor,
)
from novel_signal.modules.collection.google_serp_executor import GoogleSerpExecutor
from novel_signal.modules.collection.models import (
    CollectionFailureType,
    CollectionJobType,
    ParserVersion,
    RawEvidence,
)
from novel_signal.modules.collection.repository import CollectionRepository
from novel_signal.modules.collection.service import (
    CollectionLifecycleService,
    CollectionPlanningService,
    utc_now,
)

register_executor("amazon_in", CollectionJobType.SERP, AmazonSerpExecutor)
register_executor("amazon_in", CollectionJobType.PRODUCT_DETAIL, AmazonProductExecutor)
register_executor("google", CollectionJobType.SERP, GoogleSerpExecutor)


@dataclass(frozen=True)
class DueRunResult:
    created: int
    existing: int
    processed: int
    succeeded: int
    quarantined: int
    failed: int
    not_claimed: int
    job_ids: tuple[str, ...]


def run_collection_job(job_id: uuid.UUID, *, worker_id: str | None = None) -> dict[str, Any]:
    """Run one persisted job and always persist its lifecycle outcome."""
    current_worker = worker_id or socket.gethostname()
    with SessionLocal() as session:
        lifecycle = CollectionLifecycleService(session)
        claim = lifecycle.claim_attempt(job_id, worker_id=current_worker)
        session.commit()

    if claim is None:
        return {"job_id": str(job_id), "status": "not_claimed"}

    try:
        executor = get_executor(claim.item.platform, claim.item.job_type)
        result = execute_async(executor.execute(claim.item))
    except CollectionExecutionError as error:
        failure_type = error.failure_type
        code = error.code
        retryable = error.retryable
        details = error.details
        message = str(error)
    except TimeoutError as error:
        failure_type = CollectionFailureType.TIMEOUT
        code = "collector_timeout"
        retryable = True
        details = {}
        message = str(error) or "Collection attempt timed out"
    except ConnectionError as error:
        failure_type = CollectionFailureType.NETWORK
        code = "collector_network_error"
        retryable = True
        details = {}
        message = str(error) or "Collection network failure"
    except Exception as error:  # pragma: no cover - defensive process boundary
        failure_type = CollectionFailureType.UNKNOWN
        code = "collector_unhandled_error"
        retryable = False
        details = {"exception_type": type(error).__name__}
        message = str(error) or type(error).__name__
    else:
        with SessionLocal() as session:
            lifecycle = CollectionLifecycleService(session)
            if result.quarantine is not None:
                raw_evidence = session.get(RawEvidence, result.quarantine.raw_evidence_id)
                if raw_evidence is None:
                    raise RuntimeError("Quarantine decision references missing raw evidence")
                parser_version = (
                    session.get(ParserVersion, result.quarantine.parser_version_id)
                    if result.quarantine.parser_version_id is not None
                    else None
                )
                lifecycle.mark_quarantined(
                    claim.job.id,
                    claim.attempt.id,
                    raw_evidence=raw_evidence,
                    parser_version=parser_version,
                    failure_type=result.quarantine.failure_type,
                    reason_code=result.quarantine.reason_code,
                    reason=result.quarantine.reason,
                    schema_errors=list(result.quarantine.schema_errors),
                    parsed_payload=result.quarantine.parsed_payload,
                )
                session.commit()
                return {"job_id": str(job_id), "status": "quarantined"}

            lifecycle.mark_succeeded(claim.job.id, claim.attempt.id, metadata=result.metadata)
            session.commit()
        return {"job_id": str(job_id), "status": "succeeded"}

    with SessionLocal() as session:
        decision = CollectionLifecycleService(session).mark_failed(
            claim.job.id,
            claim.attempt.id,
            failure_type=failure_type,
            code=code,
            message=message,
            retryable=retryable,
            details=details,
        )
        session.commit()
    return {
        "job_id": str(job_id),
        "status": "retry_scheduled" if decision.should_retry else "failed",
        "error_code": code,
        "retry_after_seconds": decision.retry_after_seconds,
    }


def run_due_collection_jobs(*, max_jobs: int, worker_id: str | None = None) -> DueRunResult:
    """Plan and synchronously process a bounded due batch for one cron run."""
    if max_jobs < 1:
        raise ValueError("max_jobs must be at least 1")

    with SessionLocal() as session:
        planned = CollectionPlanningService(session).plan_due()
        session.commit()
        jobs = CollectionRepository(session).pending_dispatch_jobs(now=utc_now(), limit=max_jobs)
        job_ids = tuple(str(job.id) for job in jobs)

    outcomes = [run_collection_job(uuid.UUID(job_id), worker_id=worker_id) for job_id in job_ids]
    statuses = [str(outcome["status"]) for outcome in outcomes]
    return DueRunResult(
        created=planned.created,
        existing=planned.existing,
        processed=len(outcomes),
        succeeded=statuses.count("succeeded"),
        quarantined=statuses.count("quarantined"),
        failed=statuses.count("failed") + statuses.count("retry_scheduled"),
        not_claimed=statuses.count("not_claimed"),
        job_ids=job_ids,
    )
