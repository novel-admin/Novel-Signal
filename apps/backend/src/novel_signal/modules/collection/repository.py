from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from novel_signal.modules.collection.models import (
    CollectionAttempt,
    CollectionFailure,
    CollectionFailureType,
    CollectionJob,
    CollectionJobStatus,
    CollectionJobType,
    DataQualityCheck,
    DataQualityCheckType,
    DataQualityStatus,
    ParserVersion,
    QuarantineRecord,
    QuarantineStatus,
    RawEvidence,
)
from novel_signal.modules.keywords.models import Keyword, KeywordTrackingStatus, TrackingTarget
from novel_signal.modules.universe.models import CompetitorProduct, Marketplace, Product


class CollectionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_job(self, job_id: uuid.UUID, *, for_update: bool = False) -> CollectionJob | None:
        statement = select(CollectionJob).where(CollectionJob.id == job_id)
        if for_update:
            statement = statement.with_for_update()
        return self.session.scalar(statement)

    def get_job_by_key(self, idempotency_key: str) -> CollectionJob | None:
        return self.session.scalar(
            select(CollectionJob).where(CollectionJob.idempotency_key == idempotency_key)
        )

    def create_job_if_absent(self, job: CollectionJob) -> tuple[CollectionJob, bool]:
        existing = self.get_job_by_key(job.idempotency_key)
        if existing is not None:
            return existing, False

        try:
            with self.session.begin_nested():
                self.session.add(job)
                self.session.flush()
            return job, True
        except IntegrityError:
            existing = self.get_job_by_key(job.idempotency_key)
            if existing is None:
                raise
            return existing, False

    def list_jobs(
        self,
        *,
        limit: int,
        offset: int,
        status: CollectionJobStatus | None = None,
        job_type: CollectionJobType | None = None,
        platform: str | None = None,
    ) -> tuple[list[CollectionJob], int]:
        statement: Select[tuple[CollectionJob]] = select(CollectionJob)
        count_statement = select(func.count()).select_from(CollectionJob)
        conditions: list[ColumnElement[bool]] = []
        if status is not None:
            conditions.append(CollectionJob.status == status)
        if job_type is not None:
            conditions.append(CollectionJob.job_type == job_type)
        if platform is not None:
            conditions.append(CollectionJob.platform == platform)
        if conditions:
            statement = statement.where(*conditions)
            count_statement = count_statement.where(*conditions)
        statement = (
            statement.order_by(CollectionJob.scheduled_for.desc()).limit(limit).offset(offset)
        )
        return list(self.session.scalars(statement)), int(self.session.scalar(count_statement) or 0)

    def active_serp_targets(self) -> list[TrackingTarget]:
        statement = (
            select(TrackingTarget)
            .join(TrackingTarget.keyword)
            .where(
                TrackingTarget.archived_at.is_(None),
                TrackingTarget.enabled.is_(True),
                Keyword.archived_at.is_(None),
                Keyword.tracking_status == KeywordTrackingStatus.ACTIVE,
                Keyword.marketplace == Marketplace.AMAZON_IN,
            )
            .order_by(TrackingTarget.keyword_id, TrackingTarget.cadence_minutes)
        )
        return list(self.session.scalars(statement))

    def active_products(self) -> list[Product]:
        return list(
            self.session.scalars(
                select(Product)
                .where(
                    Product.archived_at.is_(None),
                    Product.marketplace == Marketplace.AMAZON_IN,
                    Product.marketplace_product_id.is_not(None),
                )
                .order_by(Product.id)
            )
        )

    def active_competitor_products(self) -> list[CompetitorProduct]:
        return list(
            self.session.scalars(
                select(CompetitorProduct)
                .where(
                    CompetitorProduct.archived_at.is_(None),
                    CompetitorProduct.marketplace == Marketplace.AMAZON_IN,
                    CompetitorProduct.marketplace_product_id.is_not(None),
                )
                .order_by(CompetitorProduct.id)
            )
        )

    def add_attempt(self, attempt: CollectionAttempt) -> None:
        self.session.add(attempt)
        self.session.flush()

    def add_failure(self, failure: CollectionFailure) -> None:
        self.session.add(failure)
        self.session.flush()

    def get_parser_version(
        self, platform: str, page_type: str, version: str
    ) -> ParserVersion | None:
        return self.session.scalar(
            select(ParserVersion).where(
                ParserVersion.platform == platform,
                ParserVersion.page_type == page_type,
                ParserVersion.version == version,
            )
        )

    def add_raw_evidence(self, evidence: RawEvidence) -> None:
        self.session.add(evidence)
        self.session.flush()

    def add_quarantine(self, record: QuarantineRecord) -> None:
        self.session.add(record)
        self.session.flush()

    def add_data_quality_check(self, check: DataQualityCheck) -> None:
        self.session.add(check)
        self.session.flush()

    def list_raw_evidence(
        self,
        *,
        limit: int,
        offset: int,
        job_id: uuid.UUID | None = None,
    ) -> tuple[list[RawEvidence], int]:
        statement = select(RawEvidence)
        count_statement = select(func.count()).select_from(RawEvidence)
        if job_id is not None:
            statement = statement.where(RawEvidence.job_id == job_id)
            count_statement = count_statement.where(RawEvidence.job_id == job_id)
        statement = statement.order_by(RawEvidence.captured_at.desc()).limit(limit).offset(offset)
        return list(self.session.scalars(statement)), int(self.session.scalar(count_statement) or 0)

    def list_quarantine_records(
        self,
        *,
        limit: int,
        offset: int,
        status: QuarantineStatus | None = None,
        job_id: uuid.UUID | None = None,
    ) -> tuple[list[QuarantineRecord], int]:
        statement = select(QuarantineRecord)
        count_statement = select(func.count()).select_from(QuarantineRecord)
        conditions: list[ColumnElement[bool]] = []
        if status is not None:
            conditions.append(QuarantineRecord.status == status)
        if job_id is not None:
            conditions.append(QuarantineRecord.job_id == job_id)
        if conditions:
            statement = statement.where(*conditions)
            count_statement = count_statement.where(*conditions)
        statement = (
            statement.order_by(QuarantineRecord.created_at.desc()).limit(limit).offset(offset)
        )
        return list(self.session.scalars(statement)), int(self.session.scalar(count_statement) or 0)

    def list_data_quality_checks(
        self,
        *,
        limit: int,
        offset: int,
        scope_type: str | None = None,
        scope_key: str | None = None,
    ) -> tuple[list[DataQualityCheck], int]:
        statement = select(DataQualityCheck)
        count_statement = select(func.count()).select_from(DataQualityCheck)
        conditions: list[ColumnElement[bool]] = []
        if scope_type is not None:
            conditions.append(DataQualityCheck.scope_type == scope_type)
        if scope_key is not None:
            conditions.append(DataQualityCheck.scope_key == scope_key)
        if conditions:
            statement = statement.where(*conditions)
            count_statement = count_statement.where(*conditions)
        statement = (
            statement.order_by(DataQualityCheck.created_at.desc()).limit(limit).offset(offset)
        )
        return list(self.session.scalars(statement)), int(self.session.scalar(count_statement) or 0)

    def pending_dispatch_jobs(self, *, now: datetime, limit: int = 200) -> list[CollectionJob]:
        statement = (
            select(CollectionJob)
            .where(
                CollectionJob.status == CollectionJobStatus.PENDING,
                CollectionJob.scheduled_for <= now,
                (CollectionJob.not_before.is_(None) | (CollectionJob.not_before <= now)),
            )
            .order_by(CollectionJob.scheduled_for, CollectionJob.created_at)
            .limit(limit)
        )
        return list(self.session.scalars(statement))

    def job_status_counts(
        self,
        *,
        since: datetime,
        until: datetime,
    ) -> dict[CollectionJobStatus, int]:
        rows = self.session.execute(
            select(CollectionJob.status, func.count())
            .where(
                CollectionJob.scheduled_for >= since,
                CollectionJob.scheduled_for <= until,
            )
            .group_by(CollectionJob.status)
        ).all()

        return {status: int(count) for status, count in rows}

    def challenge_failure_count(
        self,
        *,
        since: datetime,
    ) -> int:
        return int(
            self.session.scalar(
                select(func.count())
                .select_from(CollectionFailure)
                .where(
                    CollectionFailure.occurred_at >= since,
                    CollectionFailure.failure_type == CollectionFailureType.CHALLENGE,
                )
            )
            or 0
        )

    def parser_canary_failure_count(
        self,
        *,
        since: datetime,
    ) -> int:
        return int(
            self.session.scalar(
                select(func.count())
                .select_from(DataQualityCheck)
                .where(
                    DataQualityCheck.created_at >= since,
                    DataQualityCheck.status == DataQualityStatus.FAIL,
                    DataQualityCheck.check_type.in_(
                        [
                            DataQualityCheckType.FIELD_FILL_RATE,
                            DataQualityCheckType.ROW_COUNT,
                            DataQualityCheckType.VALUE_DISTRIBUTION,
                        ]
                    ),
                )
            )
            or 0
        )

    def latest_success_at(self) -> datetime | None:
        return self.session.scalar(
            select(func.max(CollectionJob.completed_at)).where(
                CollectionJob.status == CollectionJobStatus.SUCCEEDED
            )
        )

    def terminal_failures(
        self,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[CollectionJob], int]:
        condition = CollectionJob.status.in_(
            [
                CollectionJobStatus.FAILED,
                CollectionJobStatus.QUARANTINED,
            ]
        )

        statement = (
            select(CollectionJob)
            .where(condition)
            .order_by(
                CollectionJob.completed_at.desc(),
                CollectionJob.created_at.desc(),
            )
            .limit(limit)
            .offset(offset)
        )

        count_statement = select(func.count()).select_from(CollectionJob).where(condition)

        return (
            list(self.session.scalars(statement)),
            int(self.session.scalar(count_statement) or 0),
        )

    def raw_retention_candidates(
        self,
        *,
        before: datetime,
        limit: int = 200,
    ) -> list[RawEvidence]:
        return list(
            self.session.scalars(
                select(RawEvidence)
                .where(RawEvidence.captured_at < before)
                .order_by(RawEvidence.captured_at)
                .limit(limit)
            )
        )
