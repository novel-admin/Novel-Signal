# ruff: noqa: B008

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from novel_signal.db import get_db

from . import service
from .models import Capture, CollectionJob
from .schemas import (
    CaptureCreate,
    CaptureRead,
    CollectionJobCreate,
    CollectionJobRead,
    ObservationCreate,
    ObservationRead,
)

router = APIRouter(prefix="/collection", tags=["S12 Collection"])


@router.get("/meta")
def module_meta() -> dict[str, str]:
    return {"module": "S12 Collection", "owner": "Akanksh", "status": "implemented"}


@router.post("/captures", response_model=CaptureRead, status_code=status.HTTP_201_CREATED)
def capture(data: CaptureCreate, session: Session = Depends(get_db)) -> CaptureRead:
    return CaptureRead.model_validate(service.create_capture(session, data))


@router.post("/observations", response_model=ObservationRead, status_code=status.HTTP_201_CREATED)
def observation(data: ObservationCreate, session: Session = Depends(get_db)) -> ObservationRead:
    try:
        return ObservationRead.model_validate(service.publish_observation(session, data))
    except service.CollectionConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/jobs", response_model=CollectionJobRead, status_code=status.HTTP_201_CREATED)
def job(data: CollectionJobCreate, session: Session = Depends(get_db)) -> CollectionJobRead:
    return CollectionJobRead.model_validate(service.schedule_job(session, data))


@router.get("/jobs", response_model=list[CollectionJobRead])
def jobs(session: Session = Depends(get_db)) -> list[CollectionJobRead]:
    return [
        CollectionJobRead.model_validate(item)
        for item in session.scalars(
            select(CollectionJob).order_by(CollectionJob.scheduled_at.desc())
        )
    ]


@router.get("/captures", response_model=list[CaptureRead])
def captures(session: Session = Depends(get_db)) -> list[CaptureRead]:
    return [
        CaptureRead.model_validate(item)
        for item in session.scalars(select(Capture).order_by(Capture.captured_at.desc()))
    ]
