from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from novel_signal.db import get_db
from novel_signal.modules.collection.models import (
    CollectionJobStatus,
    CollectionJobType,
    QuarantineStatus,
)
from novel_signal.modules.collection.ops import (
    CollectionOperationsService,
    runtime_readiness,
)
from novel_signal.modules.collection.repository import CollectionRepository
from novel_signal.modules.collection.schemas import (
    CollectionDispatchResult,
    CollectionFailureList,
    CollectionHealthRead,
    CollectionJobList,
    CollectionJobRead,
    CollectionPlanResult,
    CollectionReadinessRead,
    DataQualityCheckList,
    DataQualityCheckRead,
    QuarantineRecordList,
    QuarantineRecordRead,
    RawEvidenceList,
    RawEvidenceRead,
    RawRetentionCandidateRead,
    RawRetentionRead,
)
from novel_signal.modules.collection.service import (
    CollectionJobNotFoundError,
    CollectionLifecycleService,
    CollectionPlanningService,
)

router = APIRouter(prefix="/collection", tags=["S12 Collection"])
SessionDep = Annotated[Session, Depends(get_db)]
Limit = Annotated[int, Query(ge=1, le=200)]
Offset = Annotated[int, Query(ge=0)]


class ResyncRequest(BaseModel):
    sources: list[str] = Field(default_factory=list, max_length=8)
    entity_ids: list[uuid.UUID] = Field(default_factory=list, max_length=200)
    window_start: datetime | None = None
    window_end: datetime | None = None

    @model_validator(mode="after")
    def validate_window(self) -> ResyncRequest:
        if (self.window_start is None) != (self.window_end is None):
            raise ValueError("window_start and window_end must be supplied together")
        if self.window_start is not None and self.window_end is not None:
            start = self.window_start.astimezone(UTC)
            end = self.window_end.astimezone(UTC)
            if start > end:
                raise ValueError("window_start must be before window_end")
            if end - start > timedelta(days=31):
                raise ValueError("Resync window cannot exceed 31 days")
        return self


@router.post("/resync", response_model=CollectionPlanResult)
def resync(request: ResyncRequest, session: SessionDep) -> CollectionPlanResult:
    source_platforms = {
        "amazon_public": "amazon_in",
        "amazon_public_pages": "amazon_in",
        "google_public": "google",
        "google_serp": "google",
        "amazon_in": "amazon_in",
        "google": "google",
    }
    unknown_sources = sorted(set(request.sources) - source_platforms.keys())
    if unknown_sources:
        raise HTTPException(
            422,
            detail={"code": "unsupported_resync_source", "sources": unknown_sources},
        )
    platforms = {source_platforms[source] for source in request.sources} or None
    result = CollectionPlanningService(session).plan_due(
        platforms=platforms,
        entity_ids=set(request.entity_ids) or None,
    )
    session.commit()
    return CollectionPlanResult(
        created=result.created,
        existing=result.existing,
        job_ids=[job.id for job in result.jobs],
    )


@router.get("/meta")
def module_meta() -> dict[str, str]:
    return {"module": "S12 Collection", "status": "phase-4"}


@router.get("/jobs", response_model=CollectionJobList)
def list_jobs(
    session: SessionDep,
    limit: Limit = 50,
    offset: Offset = 0,
    status: CollectionJobStatus | None = None,
    job_type: CollectionJobType | None = None,
    platform: str | None = None,
) -> CollectionJobList:
    items, total = CollectionRepository(session).list_jobs(
        limit=limit,
        offset=offset,
        status=status,
        job_type=job_type,
        platform=platform,
    )
    return CollectionJobList(
        items=[CollectionJobRead.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/jobs/{job_id}", response_model=CollectionJobRead)
def get_job(job_id: uuid.UUID, session: SessionDep) -> CollectionJobRead:
    try:
        job = CollectionLifecycleService(session).get_job(job_id)
    except CollectionJobNotFoundError as error:
        raise HTTPException(
            404,
            detail={"code": "collection_job_not_found", "message": "Collection job not found"},
        ) from error
    return CollectionJobRead.model_validate(job)


@router.post("/plan", response_model=CollectionPlanResult)
def plan_jobs(session: SessionDep) -> CollectionPlanResult:
    result = CollectionPlanningService(session).plan_due()
    session.commit()
    return CollectionPlanResult(
        created=result.created,
        existing=result.existing,
        job_ids=[job.id for job in result.jobs],
    )


@router.post("/jobs/{job_id}/dispatch", response_model=CollectionDispatchResult)
def dispatch_job(job_id: uuid.UUID, session: SessionDep) -> CollectionDispatchResult:
    try:
        job = CollectionLifecycleService(session).get_job(job_id)
    except CollectionJobNotFoundError as error:
        raise HTTPException(
            404,
            detail={"code": "collection_job_not_found", "message": "Collection job not found"},
        ) from error
    if job.status != CollectionJobStatus.PENDING:
        raise HTTPException(
            409,
            detail={
                "code": "collection_job_not_dispatchable",
                "message": f"Collection job is {job.status.value}, not pending",
            },
        )
    # Render Cron claims pending jobs from PostgreSQL.  This endpoint records
    # intent only; it never starts a long-running browser or source request in
    # the API process.
    return CollectionDispatchResult(dispatched=1, job_ids=[job.id])


@router.get("/raw-evidence", response_model=RawEvidenceList)
def list_raw_evidence(
    session: SessionDep,
    limit: Limit = 50,
    offset: Offset = 0,
    job_id: uuid.UUID | None = None,
) -> RawEvidenceList:
    items, total = CollectionRepository(session).list_raw_evidence(
        limit=limit, offset=offset, job_id=job_id
    )
    return RawEvidenceList(
        items=[RawEvidenceRead.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/quarantine", response_model=QuarantineRecordList)
def list_quarantine_records(
    session: SessionDep,
    limit: Limit = 50,
    offset: Offset = 0,
    status: QuarantineStatus | None = None,
    job_id: uuid.UUID | None = None,
) -> QuarantineRecordList:
    items, total = CollectionRepository(session).list_quarantine_records(
        limit=limit, offset=offset, status=status, job_id=job_id
    )
    return QuarantineRecordList(
        items=[QuarantineRecordRead.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/data-quality", response_model=DataQualityCheckList)
def list_data_quality_checks(
    session: SessionDep,
    limit: Limit = 50,
    offset: Offset = 0,
    scope_type: str | None = None,
    scope_key: str | None = None,
) -> DataQualityCheckList:
    items, total = CollectionRepository(session).list_data_quality_checks(
        limit=limit,
        offset=offset,
        scope_type=scope_type,
        scope_key=scope_key,
    )
    return DataQualityCheckList(
        items=[DataQualityCheckRead.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/health", response_model=CollectionHealthRead)
def collection_health(session: SessionDep) -> CollectionHealthRead:
    return CollectionHealthRead.model_validate(
        CollectionOperationsService(session).health(),
        from_attributes=True,
    )


@router.get("/readiness", response_model=CollectionReadinessRead)
def collection_readiness(session: SessionDep) -> CollectionReadinessRead:
    return CollectionReadinessRead.model_validate(runtime_readiness(session))


@router.get("/failures", response_model=CollectionFailureList)
def list_terminal_failures(
    session: SessionDep,
    limit: Limit = 50,
    offset: Offset = 0,
) -> CollectionFailureList:
    items, total = CollectionRepository(session).terminal_failures(
        limit=limit,
        offset=offset,
    )

    return CollectionFailureList(
        items=[CollectionJobRead.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/retention", response_model=RawRetentionRead)
def raw_retention(
    session: SessionDep,
    limit: Limit = 50,
) -> RawRetentionRead:
    service = CollectionOperationsService(session)
    cutoff, candidates = service.retention(limit=limit)

    return RawRetentionRead(
        retention_days=service.settings.raw_evidence_retention_days,
        cutoff=cutoff,
        candidates=[
            RawRetentionCandidateRead(
                id=item.id,
                job_id=item.job_id,
                captured_at=item.captured_at,
                storage_bucket=item.storage_bucket,
                object_key=item.object_key,
                byte_length=item.byte_length,
            )
            for item in candidates
        ],
        candidate_count=len(candidates),
    )
