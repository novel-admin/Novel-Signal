from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from novel_signal.modules.actions.schemas import ChangeEventCreate
from novel_signal.modules.actions.service import create_change

from .models import Capture, CollectionJob, Observation
from .schemas import CaptureCreate, CollectionJobCreate, ObservationCreate


class CollectionConflict(Exception):
    pass


def create_capture(session: Session, data: CaptureCreate) -> Capture:
    capture = Capture(**data.model_dump())
    session.add(capture)
    session.commit()
    session.refresh(capture)
    return capture


def publish_observation(session: Session, data: ObservationCreate) -> Observation:
    capture = session.get(Capture, data.capture_id)
    if not capture:
        raise CollectionConflict("capture not found")
    if capture.status != "captured":
        raise CollectionConflict("only captured responses can be published")
    observation = Observation(**data.model_dump())
    previous = session.scalar(
        select(Observation)
        .where(
            Observation.target_type == data.target_type,
            Observation.target_id == data.target_id,
            Observation.observation_type == data.observation_type,
            Observation.publication_status == "published",
        )
        .order_by(Observation.observed_at.desc())
    )
    session.add(observation)
    session.commit()
    session.refresh(observation)
    if previous and previous.value != observation.value:
        field = next(iter(set(previous.value) | set(observation.value)), "value")
        create_change(
            session,
            ChangeEventCreate(
                target_type=data.target_type,
                target_id=data.target_id,
                event_type=f"{data.observation_type}_changed",
                fingerprint=f"{data.target_id}:{data.observation_type}:{previous.id}:{observation.id}",
                old_observation_type=data.observation_type,
                old_observation_id=previous.id,
                new_observation_type=data.observation_type,
                new_observation_id=observation.id,
                field_name=field,
                old_value=previous.value.get(field),
                new_value=observation.value.get(field),
                detected_at=datetime.now(UTC),
                severity="warning",
            ),
        )
    return observation


def schedule_job(session: Session, data: CollectionJobCreate) -> CollectionJob:
    existing = session.scalar(select(CollectionJob).where(CollectionJob.job_key == data.job_key))
    if existing:
        return existing
    job = CollectionJob(**data.model_dump())
    session.add(job)
    session.commit()
    session.refresh(job)
    return job
