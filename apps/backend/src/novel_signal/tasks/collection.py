from __future__ import annotations

import socket
import uuid
from typing import Any

from novel_signal.db import SessionLocal
from novel_signal.modules.collection.amazon_serp_executor import AmazonSerpExecutor
from novel_signal.modules.collection.execution import (
    CollectionExecutionError,
    execute_async,
    get_executor,
    register_executor,
)
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
from novel_signal.tasks.celery_app import celery_app

register_executor("amazon_in", CollectionJobType.SERP, AmazonSerpExecutor)


def _worker_id(task: Any) -> str:
    hostname = getattr(getattr(task, "request", None), "hostname", None)
    return str(hostname or socket.gethostname())


@celery_app.task(  # type: ignore[untyped-decorator]
    bind=True,
    name="novel_signal.collection.run_job",
)
def run_collection_job(task: Any, job_id: str) -> dict[str, Any]:
    parsed_job_id = uuid.UUID(job_id)

    with SessionLocal() as session:
        lifecycle = CollectionLifecycleService(session)
        claim = lifecycle.claim_attempt(parsed_job_id, worker_id=_worker_id(task))
        session.commit()

    if claim is None:
        return {"job_id": job_id, "status": "not_claimed"}

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
    except Exception as error:
        failure_type = CollectionFailureType.UNKNOWN
        code = "collector_unhandled_error"
        retryable = False
        details = {"exception_type": type(error).__name__}
        message = str(error) or type(error).__name__
    else:
        with SessionLocal() as session:
            lifecycle = CollectionLifecycleService(session)

            if result.quarantine is not None:
                raw_evidence = session.get(
                    RawEvidence,
                    result.quarantine.raw_evidence_id,
                )
                if raw_evidence is None:
                    raise RuntimeError("Quarantine decision references missing raw evidence")

                parser_version = (
                    session.get(
                        ParserVersion,
                        result.quarantine.parser_version_id,
                    )
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

                return {
                    "job_id": job_id,
                    "status": "quarantined",
                }

            lifecycle.mark_succeeded(
                claim.job.id,
                claim.attempt.id,
                metadata=result.metadata,
            )
            session.commit()

        return {"job_id": job_id, "status": "succeeded"}

    with SessionLocal() as session:
        lifecycle = CollectionLifecycleService(session)
        decision = lifecycle.mark_failed(
            claim.job.id,
            claim.attempt.id,
            failure_type=failure_type,
            code=code,
            message=message,
            retryable=retryable,
            details=details,
        )
        session.commit()

    if decision.should_retry and decision.retry_after_seconds is not None:
        raise task.retry(
            countdown=decision.retry_after_seconds,
            max_retries=max(claim.job.max_attempts - 1, 0),
        )

    return {"job_id": job_id, "status": "failed", "error_code": code}


@celery_app.task(  # type: ignore[untyped-decorator]
    name="novel_signal.collection.plan_due",
)
def plan_due_collection_jobs() -> dict[str, Any]:
    with SessionLocal() as session:
        result = CollectionPlanningService(session).plan_due()
        session.commit()

    with SessionLocal() as session:
        pending = CollectionRepository(session).pending_dispatch_jobs(now=utc_now())
        job_ids = [str(job.id) for job in pending]

    for job_id in job_ids:
        run_collection_job.delay(job_id)

    return {
        "created": result.created,
        "existing": result.existing,
        "dispatched": len(job_ids),
        "job_ids": job_ids,
    }
