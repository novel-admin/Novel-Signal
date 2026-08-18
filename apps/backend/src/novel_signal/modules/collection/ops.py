from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import boto3  # type: ignore[import-untyped]
from botocore.exceptions import BotoCoreError, ClientError  # type: ignore[import-untyped]
from redis import Redis
from sqlalchemy import text
from sqlalchemy.orm import Session

from novel_signal.config import Settings, get_settings
from novel_signal.modules.collection.models import CollectionJobStatus, RawEvidence
from novel_signal.modules.collection.repository import CollectionRepository
from novel_signal.tasks.celery_app import celery_app


@dataclass(frozen=True)
class HealthSnapshot:
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


class CollectionOperationsService:
    def __init__(
        self,
        session: Session,
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self.repository = CollectionRepository(session)
        self.settings = settings or get_settings()

    def health(
        self,
        *,
        at: datetime | None = None,
    ) -> HealthSnapshot:
        now = (at or datetime.now(UTC)).astimezone(UTC)
        since = now - timedelta(hours=self.settings.collection_health_window_hours)

        counts = self.repository.job_status_counts(
            since=since,
            until=now,
        )

        pending = counts.get(CollectionJobStatus.PENDING, 0)
        running = counts.get(CollectionJobStatus.RUNNING, 0)
        succeeded = counts.get(CollectionJobStatus.SUCCEEDED, 0)
        failed = counts.get(CollectionJobStatus.FAILED, 0)
        quarantined = counts.get(
            CollectionJobStatus.QUARANTINED,
            0,
        )
        cancelled = counts.get(CollectionJobStatus.CANCELLED, 0)

        scheduled = sum(counts.values())
        terminal = succeeded + failed + quarantined + cancelled

        success_ratio = succeeded / terminal if terminal else None

        challenge_count = self.repository.challenge_failure_count(since=since)

        challenge_ratio = challenge_count / terminal if terminal else None

        parser_canary_failures = self.repository.parser_canary_failure_count(since=since)

        latest_success_at = self.repository.latest_success_at()

        freshness_minutes = (
            max(
                (now - latest_success_at.astimezone(UTC)).total_seconds() / 60.0,
                0.0,
            )
            if latest_success_at is not None
            else None
        )

        freshness_status = (
            "pass"
            if freshness_minutes is not None
            and freshness_minutes <= self.settings.collector_freshness_warn_minutes
            else "warn"
        )

        completeness_status = (
            "pass"
            if success_ratio is not None
            and success_ratio >= self.settings.collector_completeness_warn_ratio
            else "warn"
        )

        failure_ratio = (failed + quarantined) / terminal if terminal else None

        overall_status = "pass"

        if (
            freshness_status != "pass"
            or completeness_status != "pass"
            or parser_canary_failures > 0
            or (
                failure_ratio is not None
                and failure_ratio >= self.settings.collector_failure_rate_warn_threshold
            )
        ):
            overall_status = "warn"

        return HealthSnapshot(
            window_hours=self.settings.collection_health_window_hours,
            scheduled=scheduled,
            succeeded=succeeded,
            failed=failed,
            quarantined=quarantined,
            running=running,
            pending=pending,
            terminal=terminal,
            success_ratio=success_ratio,
            challenge_count=challenge_count,
            challenge_ratio=challenge_ratio,
            parser_canary_failures=parser_canary_failures,
            latest_success_at=latest_success_at,
            freshness_minutes=freshness_minutes,
            freshness_status=freshness_status,
            completeness_status=completeness_status,
            overall_status=overall_status,
        )

    def retention(
        self,
        *,
        at: datetime | None = None,
        limit: int = 200,
    ) -> tuple[datetime, list[RawEvidence]]:
        now = (at or datetime.now(UTC)).astimezone(UTC)

        cutoff = now - timedelta(days=self.settings.raw_evidence_retention_days)

        candidates = self.repository.raw_retention_candidates(
            before=cutoff,
            limit=limit,
        )

        return cutoff, candidates


def _readiness_item(
    status: str,
    detail: str | None = None,
) -> dict[str, str | None]:
    return {
        "status": status,
        "detail": detail,
    }


def runtime_readiness(
    session: Session,
    settings: Settings | None = None,
) -> dict[str, object]:
    config = settings or get_settings()

    results: dict[
        str,
        dict[str, str | None],
    ] = {}

    # PostgreSQL
    try:
        session.execute(text("SELECT 1"))
        results["postgres"] = _readiness_item("ready")

    except Exception as error:  # pragma: no cover
        results["postgres"] = _readiness_item(
            "down",
            type(error).__name__,
        )

    # Redis
    try:
        redis_client = Redis.from_url(
            config.redis_url,
            socket_connect_timeout=1,
            socket_timeout=1,
        )

        redis_client.ping()

        results["redis"] = _readiness_item("ready")

    except Exception as error:  # pragma: no cover
        results["redis"] = _readiness_item(
            "down",
            type(error).__name__,
        )

    # MinIO / S3-compatible storage
    try:
        s3 = boto3.client(
            "s3",
            endpoint_url=config.object_store_endpoint,
            aws_access_key_id=(config.object_store_access_key.get_secret_value()),
            aws_secret_access_key=(config.object_store_secret_key.get_secret_value()),
            region_name=config.object_store_region,
        )

        s3.head_bucket(Bucket=config.object_store_bucket)

        results["object_store"] = _readiness_item("ready")

    except ClientError as error:
        code = str(error.response.get("Error", {}).get("Code", "ClientError"))

        if code in {
            "404",
            "NoSuchBucket",
            "NotFound",
        }:
            results["object_store"] = _readiness_item(
                "degraded",
                "bucket_missing",
            )
        else:
            results["object_store"] = _readiness_item(
                "down",
                code,
            )

    except BotoCoreError as error:  # pragma: no cover
        results["object_store"] = _readiness_item(
            "down",
            type(error).__name__,
        )

    except Exception as error:  # pragma: no cover
        results["object_store"] = _readiness_item(
            "down",
            type(error).__name__,
        )

    # Celery config
    broker = str(celery_app.conf.broker_url or "")

    results["celery"] = (
        _readiness_item("ready")
        if broker
        else _readiness_item(
            "down",
            "broker_not_configured",
        )
    )

    overall = "ready" if all(item["status"] == "ready" for item in results.values()) else "degraded"

    return {
        "status": overall,
        **results,
    }
